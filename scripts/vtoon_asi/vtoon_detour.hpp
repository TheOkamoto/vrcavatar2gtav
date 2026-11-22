#pragma once
/*
 * vtoon_detour.hpp
 * ================
 * Low-level Layer 4a (Safe x64 15-Byte Factory Detours & Per-VTable COM Registry):
 * Installs verified non-RIP 15-byte x64 trampolines on `D3D11CreateDevice*` and
 * atomically patches + tracks original COM method pointers per VTable instance
 * with first-captured fallback pointers so wrapped/heap context VTables stay safe.
 */

#include "vtoon_d3d11_hook.hpp"

#include <cstring>
#include <shared_mutex>
#include <vector>

namespace gtav_vtoon {

using FnClearState = void(STDMETHODCALLTYPE*)(ID3D11DeviceContext*);
using FnDrawIndexedInstanced = void(STDMETHODCALLTYPE*)(ID3D11DeviceContext*, UINT, UINT, UINT, INT, UINT);
using FnPresent = HRESULT(STDMETHODCALLTYPE*)(IDXGISwapChain*, UINT, UINT);
using FnGetImmediateContext = void(STDMETHODCALLTYPE*)(ID3D11Device*, ID3D11DeviceContext**);
using FnScriptHookPresentCallback = void(*)(void*);
using FnPresentCallbackRegister = void(*)(FnScriptHookPresentCallback);
using FnPresentCallbackUnregister = void(*)(FnScriptHookPresentCallback);

struct ModuleAddressRange {
    uintptr_t startAddr = 0;
    uintptr_t endAddr = 0;
    bool valid = false;

    bool Contains(const void* ptrVal) const {
        if (!valid || !ptrVal) {
            return false;
        }
        const uintptr_t addrVal = reinterpret_cast<uintptr_t>(ptrVal);
        return addrVal >= startAddr && addrVal < endAddr;
    }
};

inline ModuleAddressRange QueryModuleAddressRange(const char* moduleName) {
    ModuleAddressRange outRange{};
    HMODULE modHandle = GetModuleHandleA(moduleName);
    if (!modHandle) {
        return outRange;
    }
    const uintptr_t baseAddr = reinterpret_cast<uintptr_t>(modHandle);
    const IMAGE_DOS_HEADER* dosHdr = reinterpret_cast<const IMAGE_DOS_HEADER*>(baseAddr);
    if (dosHdr->e_magic != IMAGE_DOS_SIGNATURE) {
        return outRange;
    }
    const IMAGE_NT_HEADERS* ntHdr = reinterpret_cast<const IMAGE_NT_HEADERS*>(baseAddr + dosHdr->e_lfanew);
    if (ntHdr->Signature != IMAGE_NT_SIGNATURE) {
        return outRange;
    }
    outRange.startAddr = baseAddr;
    outRange.endAddr = baseAddr + static_cast<uintptr_t>(ntHdr->OptionalHeader.SizeOfImage);
    outRange.valid = (outRange.endAddr > outRange.startAddr);
    return outRange;
}

struct OrigDeviceVTable {
    void** vtablePtr = nullptr;
    FnCreatePixelShader origCreatePixelShader = nullptr;
    FnCreateDeferredContext origCreateDeferredContext = nullptr;
    FnGetImmediateContext origGetImmediateContext = nullptr;
};

struct OrigContextVTable {
    void** vtablePtr = nullptr;
    FnPSSetShader origPSSetShader = nullptr;
    FnDrawIndexed origDrawIndexed = nullptr;
    FnDraw origDraw = nullptr;
    FnDrawInstanced origDrawInstanced = nullptr;
    FnDrawIndexedInstanced origDrawIndexedInstanced = nullptr;
    FnClearState origClearState = nullptr;
};

struct OrigSwapVTable {
    void** vtablePtr = nullptr;
    FnPresent origPresent = nullptr;
};

struct D3D11DetourRecord {
    unsigned char* targetPtr = nullptr;
    unsigned char* trampolinePtr = nullptr;
    unsigned char origBytes[15] = {};
    bool installed = false;
};

static constexpr unsigned char kExpectedD3D11Prologue[15] = {
    0x48, 0x89, 0x5C, 0x24, 0x08,
    0x48, 0x89, 0x6C, 0x24, 0x10,
    0x48, 0x89, 0x74, 0x24, 0x18
};

template <typename FnType>
inline void PatchSlotIfNeeded(
    void** vtablePtr,
    size_t slotIndex,
    FnType hookFunc,
    FnType& origOut,
    FnType& fallbackOut,
    const ModuleAddressRange& rawModuleRange
) {
    if (!vtablePtr) {
        return;
    }
    void* currentSlot = vtablePtr[slotIndex];
    if (currentSlot == reinterpret_cast<void*>(hookFunc)) {
        return;
    }
    // Preserve overlay hooks (e.g., RTSS/EOSOVH) that wrap slots after initial hook
    if (origOut != nullptr && rawModuleRange.valid && !rawModuleRange.Contains(currentSlot)) {
        return;
    }
    DWORD prevProtect = 0;
    if (!VirtualProtect(&vtablePtr[slotIndex], sizeof(void*), PAGE_EXECUTE_READWRITE, &prevProtect)) {
        return;
    }
    origOut = reinterpret_cast<FnType>(currentSlot);
    if (fallbackOut == nullptr) {
        fallbackOut = reinterpret_cast<FnType>(currentSlot);
    }
    vtablePtr[slotIndex] = reinterpret_cast<void*>(hookFunc);
    VirtualProtect(&vtablePtr[slotIndex], sizeof(void*), prevProtect, &prevProtect);
}

template <typename FnType>
inline bool InstallFixed15Detour(
    FARPROC targetProc,
    FnType detourFunc,
    D3D11DetourRecord& recordOut,
    FnType& origOut
) {
    if (!targetProc || recordOut.installed) {
        return recordOut.installed;
    }
    unsigned char* targetBytes = reinterpret_cast<unsigned char*>(targetProc);
    if (std::memcmp(targetBytes, kExpectedD3D11Prologue, 15) != 0) {
        return false;
    }
    void* trampMem = VirtualAlloc(nullptr, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!trampMem) {
        return false;
    }
    unsigned char* trampBytes = static_cast<unsigned char*>(trampMem);
    std::memcpy(trampBytes, targetBytes, 15);
    const uintptr_t resumeAddr = reinterpret_cast<uintptr_t>(targetBytes + 15);
    trampBytes[15] = 0x48;
    trampBytes[16] = 0xB8;
    std::memcpy(trampBytes + 17, &resumeAddr, sizeof(resumeAddr));
    trampBytes[25] = 0xFF;
    trampBytes[26] = 0xE0;

    std::memcpy(recordOut.origBytes, targetBytes, 15);
    DWORD prevProtect = 0;
    if (!VirtualProtect(targetBytes, 15, PAGE_EXECUTE_READWRITE, &prevProtect)) {
        VirtualFree(trampMem, 0, MEM_RELEASE);
        return false;
    }
    const uintptr_t detourAddr = reinterpret_cast<uintptr_t>(detourFunc);
    unsigned char patchBytes[15] = {};
    patchBytes[0] = 0x48;
    patchBytes[1] = 0xB8;
    std::memcpy(patchBytes + 2, &detourAddr, sizeof(detourAddr));
    patchBytes[10] = 0xFF;
    patchBytes[11] = 0xE0;
    patchBytes[12] = 0x90;
    patchBytes[13] = 0x90;
    patchBytes[14] = 0x90;

    std::memcpy(targetBytes, patchBytes, 15);
    VirtualProtect(targetBytes, 15, prevProtect, &prevProtect);
    FlushInstructionCache(GetCurrentProcess(), targetBytes, 15);

    recordOut.targetPtr = targetBytes;
    recordOut.trampolinePtr = trampBytes;
    recordOut.installed = true;
    origOut = reinterpret_cast<FnType>(trampMem);
    return true;
}

inline void RemoveFixed15Detour(D3D11DetourRecord& record) {
    if (!record.installed || !record.targetPtr) {
        return;
    }
    DWORD prevProtect = 0;
    if (VirtualProtect(record.targetPtr, 15, PAGE_EXECUTE_READWRITE, &prevProtect)) {
        if (record.targetPtr[0] == 0x48 && record.targetPtr[1] == 0xB8) {
            std::memcpy(record.targetPtr, record.origBytes, 15);
            FlushInstructionCache(GetCurrentProcess(), record.targetPtr, 15);
        }
        VirtualProtect(record.targetPtr, 15, prevProtect, &prevProtect);
    }
    if (record.trampolinePtr) {
        VirtualFree(record.trampolinePtr, 0, MEM_RELEASE);
        record.trampolinePtr = nullptr;
    }
    record.installed = false;
}

/** Thread-safe shared-read VTable hook installer & lookup registry with fallbacks. */
class VTableRegistry {
public:
    VTableRegistry() {
        deviceTables_.reserve(16);
        contextTables_.reserve(64);
        swapTables_.reserve(16);
    }

    void InstallOrUpdateDevice(
        void** devVtbl,
        FnCreatePixelShader hookPs,
        FnCreateDeferredContext hookDefCtx,
        FnGetImmediateContext hookGetImm
    ) {
        if (!devVtbl) return;
        std::unique_lock<std::shared_mutex> writeLock(registryMutex_);
        EnsureRangesLoaded();
        OrigDeviceVTable* targetEntry = nullptr;
        for (OrigDeviceVTable& item : deviceTables_) {
            if (item.vtablePtr == devVtbl) {
                targetEntry = &item;
                break;
            }
        }
        if (!targetEntry) {
            deviceTables_.push_back(OrigDeviceVTable{devVtbl});
            targetEntry = &deviceTables_.back();
        }
        PatchSlotIfNeeded(devVtbl, 15, hookPs, targetEntry->origCreatePixelShader, fallbackDevice_.origCreatePixelShader, d3d11Range_);
        PatchSlotIfNeeded(devVtbl, 27, hookDefCtx, targetEntry->origCreateDeferredContext, fallbackDevice_.origCreateDeferredContext, d3d11Range_);
        PatchSlotIfNeeded(devVtbl, 40, hookGetImm, targetEntry->origGetImmediateContext, fallbackDevice_.origGetImmediateContext, d3d11Range_);
    }

    void InstallOrUpdateContext(
        void** ctxVtbl,
        FnPSSetShader hookPs,
        FnDrawIndexed hookDrawIdx,
        FnDraw hookDraw,
        FnDrawIndexedInstanced hookDrawIdxInst,
        FnDrawInstanced hookDrawInst,
        FnClearState hookClear
    ) {
        if (!ctxVtbl) return;
        std::unique_lock<std::shared_mutex> writeLock(registryMutex_);
        EnsureRangesLoaded();
        OrigContextVTable* targetEntry = nullptr;
        for (OrigContextVTable& item : contextTables_) {
            if (item.vtablePtr == ctxVtbl) {
                targetEntry = &item;
                break;
            }
        }
        if (!targetEntry) {
            contextTables_.push_back(OrigContextVTable{ctxVtbl});
            targetEntry = &contextTables_.back();
        }
        PatchSlotIfNeeded(ctxVtbl, 9, hookPs, targetEntry->origPSSetShader, fallbackContext_.origPSSetShader, d3d11Range_);
        PatchSlotIfNeeded(ctxVtbl, 12, hookDrawIdx, targetEntry->origDrawIndexed, fallbackContext_.origDrawIndexed, d3d11Range_);
        PatchSlotIfNeeded(ctxVtbl, 13, hookDraw, targetEntry->origDraw, fallbackContext_.origDraw, d3d11Range_);
        PatchSlotIfNeeded(ctxVtbl, 20, hookDrawIdxInst, targetEntry->origDrawIndexedInstanced, fallbackContext_.origDrawIndexedInstanced, d3d11Range_);
        PatchSlotIfNeeded(ctxVtbl, 21, hookDrawInst, targetEntry->origDrawInstanced, fallbackContext_.origDrawInstanced, d3d11Range_);
        PatchSlotIfNeeded(ctxVtbl, 110, hookClear, targetEntry->origClearState, fallbackContext_.origClearState, d3d11Range_);
    }

    void InstallOrUpdateSwap(void** swapVtbl, FnPresent hookPresent) {
        if (!swapVtbl) return;
        std::unique_lock<std::shared_mutex> writeLock(registryMutex_);
        EnsureRangesLoaded();
        for (const OrigSwapVTable& item : swapTables_) {
            if (item.vtablePtr == swapVtbl) return;
        }
        OrigSwapVTable entry{};
        entry.vtablePtr = swapVtbl;
        PatchSlotIfNeeded(swapVtbl, 8, hookPresent, entry.origPresent, fallbackSwap_.origPresent, dxgiRange_);
        swapTables_.push_back(entry);
    }

    OrigDeviceVTable FindDevice(void** devVtbl) {
        std::shared_lock<std::shared_mutex> readLock(registryMutex_);
        for (const OrigDeviceVTable& item : deviceTables_) {
            if (item.vtablePtr == devVtbl) return item;
        }
        return fallbackDevice_;
    }

    OrigContextVTable FindContext(void** ctxVtbl) {
        std::shared_lock<std::shared_mutex> readLock(registryMutex_);
        for (const OrigContextVTable& item : contextTables_) {
            if (item.vtablePtr == ctxVtbl) return item;
        }
        return fallbackContext_;
    }

    OrigSwapVTable FindSwap(void** swapVtbl) {
        std::shared_lock<std::shared_mutex> readLock(registryMutex_);
        for (const OrigSwapVTable& item : swapTables_) {
            if (item.vtablePtr == swapVtbl) return item;
        }
        return fallbackSwap_;
    }

    bool ShouldSyncDeviceVTable(
        void** devVtbl,
        FnCreatePixelShader hookPs,
        FnCreateDeferredContext hookDefCtx,
        FnGetImmediateContext hookGetImm
    ) const {
        if (!devVtbl) return false;
        if (!d3d11Range_.valid) return true;
        return IsRawD3D11Slot(devVtbl[15], reinterpret_cast<const void*>(hookPs)) ||
               IsRawD3D11Slot(devVtbl[27], reinterpret_cast<const void*>(hookDefCtx)) ||
               IsRawD3D11Slot(devVtbl[40], reinterpret_cast<const void*>(hookGetImm));
    }

    bool ShouldSyncContextVTable(
        void** ctxVtbl,
        FnPSSetShader hookPs,
        FnDrawIndexed hookDrawIdx,
        FnDraw hookDraw,
        FnDrawIndexedInstanced hookDrawIdxInst,
        FnDrawInstanced hookDrawInst,
        FnClearState hookClear
    ) const {
        if (!ctxVtbl) return false;
        if (!d3d11Range_.valid) return true;
        return IsRawD3D11Slot(ctxVtbl[9], reinterpret_cast<const void*>(hookPs)) ||
               IsRawD3D11Slot(ctxVtbl[12], reinterpret_cast<const void*>(hookDrawIdx)) ||
               IsRawD3D11Slot(ctxVtbl[13], reinterpret_cast<const void*>(hookDraw)) ||
               IsRawD3D11Slot(ctxVtbl[20], reinterpret_cast<const void*>(hookDrawIdxInst)) ||
               IsRawD3D11Slot(ctxVtbl[21], reinterpret_cast<const void*>(hookDrawInst)) ||
               IsRawD3D11Slot(ctxVtbl[110], reinterpret_cast<const void*>(hookClear));
    }

private:
    bool IsRawD3D11Slot(const void* slotPtr, const void* hookPtr) const {
        return slotPtr != hookPtr && d3d11Range_.Contains(slotPtr);
    }

    void EnsureRangesLoaded() {
        if (!d3d11Range_.valid) {
            d3d11Range_ = QueryModuleAddressRange("d3d11.dll");
        }
        if (!dxgiRange_.valid) {
            dxgiRange_ = QueryModuleAddressRange("dxgi.dll");
        }
    }

    std::shared_mutex registryMutex_;
    ModuleAddressRange d3d11Range_{};
    ModuleAddressRange dxgiRange_{};
    std::vector<OrigDeviceVTable> deviceTables_;
    std::vector<OrigContextVTable> contextTables_;
    std::vector<OrigSwapVTable> swapTables_;
    OrigDeviceVTable fallbackDevice_{};
    OrigContextVTable fallbackContext_{};
    OrigSwapVTable fallbackSwap_{};
};

}  // namespace gtav_vtoon
