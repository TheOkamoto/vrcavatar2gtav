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

#include <d3d11_1.h>
#include <cstring>
#include <shared_mutex>
#include <vector>

namespace gtav_vtoon {

using FnClearState = void(STDMETHODCALLTYPE*)(ID3D11DeviceContext*);
using FnFlush = void(STDMETHODCALLTYPE*)(ID3D11DeviceContext*);
using FnExecuteCommandList = void(STDMETHODCALLTYPE*)(ID3D11DeviceContext*, ID3D11CommandList*, BOOL);
using FnDrawIndexedInstanced = void(STDMETHODCALLTYPE*)(ID3D11DeviceContext*, UINT, UINT, UINT, INT, UINT);
using FnDrawIndexedInstancedIndirect = void(STDMETHODCALLTYPE*)(ID3D11DeviceContext*, ID3D11Buffer*, UINT);
using FnDrawInstancedIndirect = void(STDMETHODCALLTYPE*)(ID3D11DeviceContext*, ID3D11Buffer*, UINT);
using FnPresent = HRESULT(STDMETHODCALLTYPE*)(IDXGISwapChain*, UINT, UINT);
using FnGetImmediateContext = void(STDMETHODCALLTYPE*)(ID3D11Device*, ID3D11DeviceContext**);
using FnGetImmediateContext1 = void(STDMETHODCALLTYPE*)(ID3D11Device1*, ID3D11DeviceContext1**);
using FnCreateDeferredContext1 = HRESULT(STDMETHODCALLTYPE*)(ID3D11Device1*, UINT, ID3D11DeviceContext1**);
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
    FnGetImmediateContext1 origGetImmediateContext1 = nullptr;
    FnCreateDeferredContext1 origCreateDeferredContext1 = nullptr;
};

struct OrigContextVTable {
    void** vtablePtr = nullptr;
    FnPSSetShader origPSSetShader = nullptr;
    FnDrawIndexed origDrawIndexed = nullptr;
    FnDraw origDraw = nullptr;
    FnDrawInstanced origDrawInstanced = nullptr;
    FnDrawIndexedInstanced origDrawIndexedInstanced = nullptr;
    FnDrawIndexedInstancedIndirect origDrawIndexedInstancedIndirect = nullptr;
    FnDrawInstancedIndirect origDrawInstancedIndirect = nullptr;
    FnClearState origClearState = nullptr;
    FnExecuteCommandList origExecuteCommandList = nullptr;
    FnFlush origFlush = nullptr;
};

struct OrigSwapVTable {
    void** vtablePtr = nullptr;
    FnPresent origPresent = nullptr;
};

struct D3D11DetourRecord {
    unsigned char* targetPtr = nullptr;
    unsigned char* trampolinePtr = nullptr;
    unsigned char origBytes[24] = {};
    size_t patchLen = 0;
    bool installed = false;
};

inline size_t MeasureSafeNonRipPrologue(const void* codePtr, size_t minBytes) {
    if (!codePtr || minBytes == 0 || minBytes > 24) return 0;
    const unsigned char* code = static_cast<const unsigned char*>(codePtr);
    size_t pos = 0;
    while (pos < minBytes) {
        size_t rem = 24 - pos;
        if (rem >= 5 && code[pos] == 0x48 && code[pos + 1] == 0x89 && code[pos + 3] == 0x24 &&
            (code[pos + 2] == 0x44 || code[pos + 2] == 0x4C || code[pos + 2] == 0x54 ||
             code[pos + 2] == 0x5C || code[pos + 2] == 0x6C || code[pos + 2] == 0x74 || code[pos + 2] == 0x7C)) {
            pos += 5;
        } else if (rem >= 5 && code[pos] == 0x4C && code[pos + 1] == 0x89 && code[pos + 3] == 0x24 &&
                   (code[pos + 2] == 0x44 || code[pos + 2] == 0x4C)) {
            pos += 5;
        } else if (rem >= 3 && code[pos] == 0x48 && code[pos + 1] == 0x8B && code[pos + 2] == 0xC4) {
            pos += 3;
        } else if (rem >= 4 && code[pos] == 0x48 && code[pos + 1] == 0x89 &&
                   (code[pos + 2] == 0x58 || code[pos + 2] == 0x68 || code[pos + 2] == 0x70 || code[pos + 2] == 0x78)) {
            pos += 4;
        } else if (rem >= 4 && code[pos] == 0x48 && code[pos + 1] == 0x8D &&
                   (code[pos + 2] == 0x68 || code[pos + 2] == 0x70)) {
            pos += 4;
        } else if (rem >= 4 && code[pos] == 0x48 && code[pos + 1] == 0x83 && code[pos + 2] == 0xEC) {
            pos += 4;
        } else if (rem >= 7 && code[pos] == 0x48 && code[pos + 1] == 0x81 && code[pos + 2] == 0xEC) {
            pos += 7;
        } else if (rem >= 2 && code[pos] == 0x40 &&
                   (code[pos + 1] == 0x53 || code[pos + 1] == 0x55 || code[pos + 1] == 0x56 || code[pos + 1] == 0x57)) {
            pos += 2;
        } else if (rem >= 2 && code[pos] == 0x41 &&
                   (code[pos + 1] == 0x54 || code[pos + 1] == 0x55 || code[pos + 1] == 0x56 || code[pos + 1] == 0x57)) {
            pos += 2;
        } else if (rem >= 1 && (code[pos] == 0x53 || code[pos] == 0x55 || code[pos] == 0x56 || code[pos] == 0x57)) {
            pos += 1;
        } else {
            return 0;
        }
        if (pos > 24) return 0;
    }
    return pos;
}

template <typename FnType>
inline bool PatchSlotIfNeeded(
    void** vtablePtr,
    size_t slotIndex,
    FnType hookFunc,
    FnType& origOut,
    FnType& fallbackOut,
    const ModuleAddressRange& rawModuleRange,
    bool forceForeignRehook = false
) {
    if (!vtablePtr) {
        return false;
    }
    void* currentSlot = vtablePtr[slotIndex];
    if (currentSlot == reinterpret_cast<void*>(hookFunc)) {
        return false;
    }
    // Preserve overlay hooks (e.g., RTSS/EOSOVH) unless foreign replacement broke draw callbacks
    if (origOut != nullptr && rawModuleRange.valid && !rawModuleRange.Contains(currentSlot)) {
        if (!forceForeignRehook || currentSlot == reinterpret_cast<void*>(origOut)) {
            return false;
        }
    }
    DWORD prevProtect = 0;
    if (!VirtualProtect(&vtablePtr[slotIndex], sizeof(void*), PAGE_EXECUTE_READWRITE, &prevProtect)) {
        return false;
    }
    origOut = reinterpret_cast<FnType>(currentSlot);
    if (fallbackOut == nullptr) {
        fallbackOut = reinterpret_cast<FnType>(currentSlot);
    }
    vtablePtr[slotIndex] = reinterpret_cast<void*>(hookFunc);
    VirtualProtect(&vtablePtr[slotIndex], sizeof(void*), prevProtect, &prevProtect);
    return true;
}

inline std::string DescribeCodeModule(const void* codePtr) {
    if (!codePtr) return "null";
    HMODULE modHandle = nullptr;
    if (!GetModuleHandleExA(
            GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
            static_cast<LPCSTR>(codePtr),
            &modHandle) || !modHandle) {
        return "dyn";
    }
    char modPath[MAX_PATH] = {};
    DWORD pathLen = GetModuleFileNameA(modHandle, modPath, MAX_PATH);
    if (pathLen == 0) return "unk";
    std::string fullStr(modPath, pathLen);
    size_t slashPos = fullStr.find_last_of("\\/");
    return (slashPos != std::string::npos) ? fullStr.substr(slashPos + 1) : fullStr;
}

template <typename FnType>
inline bool InstallSafePrologueDetour(
    void* targetAddr,
    FnType detourFunc,
    D3D11DetourRecord& recordOut,
    FnType& origOut
) {
    if (!targetAddr || recordOut.installed) {
        return recordOut.installed;
    }
    unsigned char* targetBytes = static_cast<unsigned char*>(targetAddr);
    const size_t patchLen = MeasureSafeNonRipPrologue(targetBytes, 14);
    if (patchLen < 14 || patchLen > 24) {
        return false;
    }
    void* trampMem = VirtualAlloc(nullptr, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!trampMem) {
        return false;
    }
    unsigned char* trampBytes = static_cast<unsigned char*>(trampMem);
    std::memcpy(trampBytes, targetBytes, patchLen);
    const uintptr_t resumeAddr = reinterpret_cast<uintptr_t>(targetBytes + patchLen);
    trampBytes[patchLen + 0] = 0xFF;
    trampBytes[patchLen + 1] = 0x25;
    trampBytes[patchLen + 2] = 0x00;
    trampBytes[patchLen + 3] = 0x00;
    trampBytes[patchLen + 4] = 0x00;
    trampBytes[patchLen + 5] = 0x00;
    std::memcpy(trampBytes + patchLen + 6, &resumeAddr, sizeof(resumeAddr));

    std::memcpy(recordOut.origBytes, targetBytes, patchLen);
    recordOut.patchLen = patchLen;
    DWORD prevProtect = 0;
    if (!VirtualProtect(targetBytes, patchLen, PAGE_EXECUTE_READWRITE, &prevProtect)) {
        VirtualFree(trampMem, 0, MEM_RELEASE);
        return false;
    }
    const uintptr_t detourAddr = reinterpret_cast<uintptr_t>(detourFunc);
    unsigned char patchBytes[24] = {};
    std::memset(patchBytes, 0x90, patchLen);
    patchBytes[0] = 0xFF;
    patchBytes[1] = 0x25;
    patchBytes[2] = 0x00;
    patchBytes[3] = 0x00;
    patchBytes[4] = 0x00;
    patchBytes[5] = 0x00;
    std::memcpy(patchBytes + 6, &detourAddr, sizeof(detourAddr));

    std::memcpy(targetBytes, patchBytes, patchLen);
    VirtualProtect(targetBytes, patchLen, prevProtect, &prevProtect);
    FlushInstructionCache(GetCurrentProcess(), targetBytes, patchLen);

    recordOut.targetPtr = targetBytes;
    recordOut.trampolinePtr = trampBytes;
    recordOut.installed = true;
    origOut = reinterpret_cast<FnType>(trampMem);
    return true;
}

inline void RemoveSafePrologueDetour(D3D11DetourRecord& record) {
    if (!record.installed || !record.targetPtr) {
        return;
    }
    const size_t restoreLen = (record.patchLen >= 14 && record.patchLen <= 24) ? record.patchLen : 15;
    DWORD prevProtect = 0;
    if (VirtualProtect(record.targetPtr, restoreLen, PAGE_EXECUTE_READWRITE, &prevProtect)) {
        if ((record.targetPtr[0] == 0xFF && record.targetPtr[1] == 0x25) ||
            (record.targetPtr[0] == 0x48 && record.targetPtr[1] == 0xB8)) {
            std::memcpy(record.targetPtr, record.origBytes, restoreLen);
            FlushInstructionCache(GetCurrentProcess(), record.targetPtr, restoreLen);
        }
        VirtualProtect(record.targetPtr, restoreLen, prevProtect, &prevProtect);
    }
    if (record.trampolinePtr) {
        VirtualFree(record.trampolinePtr, 0, MEM_RELEASE);
        record.trampolinePtr = nullptr;
    }
    record.patchLen = 0;
    record.installed = false;
}

template <typename FnType>
inline bool InstallFixed15Detour(
    FARPROC targetProc,
    FnType detourFunc,
    D3D11DetourRecord& recordOut,
    FnType& origOut
) {
    return InstallSafePrologueDetour(reinterpret_cast<void*>(targetProc), detourFunc, recordOut, origOut);
}

inline void RemoveFixed15Detour(D3D11DetourRecord& record) {
    RemoveSafePrologueDetour(record);
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
        FnGetImmediateContext hookGetImm,
        bool isDevice1 = false,
        FnGetImmediateContext1 hookGetImm1 = nullptr,
        FnCreateDeferredContext1 hookDefCtx1 = nullptr
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
        if (isDevice1 && hookGetImm1 && hookDefCtx1) {
            PatchSlotIfNeeded(devVtbl, 43, hookGetImm1, targetEntry->origGetImmediateContext1, fallbackDevice_.origGetImmediateContext1, d3d11Range_);
            PatchSlotIfNeeded(devVtbl, 44, hookDefCtx1, targetEntry->origCreateDeferredContext1, fallbackDevice_.origCreateDeferredContext1, d3d11Range_);
        }
    }

    uint32_t InstallOrUpdateContext(
        void** ctxVtbl,
        FnPSSetShader hookPs,
        FnDrawIndexed hookDrawIdx,
        FnDraw hookDraw,
        FnDrawIndexedInstanced hookDrawIdxInst,
        FnDrawInstanced hookDrawInst,
        FnDrawIndexedInstancedIndirect hookDrawIdxInd,
        FnDrawInstancedIndirect hookDrawInd,
        FnClearState hookClear,
        bool forceForeignRehook = false,
        FnExecuteCommandList hookExecCmd = nullptr,
        FnFlush hookFlush = nullptr
    ) {
        if (!ctxVtbl) return 0u;
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
        uint32_t patchedMask = 0u;
        if (PatchSlotIfNeeded(ctxVtbl, 9, hookPs, targetEntry->origPSSetShader, fallbackContext_.origPSSetShader, d3d11Range_, forceForeignRehook)) patchedMask |= (1u << 0);
        if (PatchSlotIfNeeded(ctxVtbl, 12, hookDrawIdx, targetEntry->origDrawIndexed, fallbackContext_.origDrawIndexed, d3d11Range_, forceForeignRehook)) patchedMask |= (1u << 1);
        if (PatchSlotIfNeeded(ctxVtbl, 13, hookDraw, targetEntry->origDraw, fallbackContext_.origDraw, d3d11Range_, forceForeignRehook)) patchedMask |= (1u << 2);
        if (PatchSlotIfNeeded(ctxVtbl, 20, hookDrawIdxInst, targetEntry->origDrawIndexedInstanced, fallbackContext_.origDrawIndexedInstanced, d3d11Range_, forceForeignRehook)) patchedMask |= (1u << 3);
        if (PatchSlotIfNeeded(ctxVtbl, 21, hookDrawInst, targetEntry->origDrawInstanced, fallbackContext_.origDrawInstanced, d3d11Range_, forceForeignRehook)) patchedMask |= (1u << 4);
        if (PatchSlotIfNeeded(ctxVtbl, 39, hookDrawIdxInd, targetEntry->origDrawIndexedInstancedIndirect, fallbackContext_.origDrawIndexedInstancedIndirect, d3d11Range_, forceForeignRehook)) patchedMask |= (1u << 5);
        if (PatchSlotIfNeeded(ctxVtbl, 40, hookDrawInd, targetEntry->origDrawInstancedIndirect, fallbackContext_.origDrawInstancedIndirect, d3d11Range_, forceForeignRehook)) patchedMask |= (1u << 6);
        if (hookExecCmd && PatchSlotIfNeeded(ctxVtbl, 55, hookExecCmd, targetEntry->origExecuteCommandList, fallbackContext_.origExecuteCommandList, d3d11Range_, forceForeignRehook)) patchedMask |= (1u << 7);
        if (PatchSlotIfNeeded(ctxVtbl, 110, hookClear, targetEntry->origClearState, fallbackContext_.origClearState, d3d11Range_, forceForeignRehook)) patchedMask |= (1u << 8);
        if (hookFlush && PatchSlotIfNeeded(ctxVtbl, 111, hookFlush, targetEntry->origFlush, fallbackContext_.origFlush, d3d11Range_, forceForeignRehook)) patchedMask |= (1u << 9);
        return patchedMask;
    }

    void ResyncKnownContexts(
        FnPSSetShader hookPs,
        FnDrawIndexed hookDrawIdx,
        FnDraw hookDraw,
        FnDrawIndexedInstanced hookDrawIdxInst,
        FnDrawInstanced hookDrawInst,
        FnDrawIndexedInstancedIndirect hookDrawIdxInd,
        FnDrawInstancedIndirect hookDrawInd,
        FnClearState hookClear,
        bool forceForeignRehook,
        FnExecuteCommandList hookExecCmd = nullptr,
        FnFlush hookFlush = nullptr
    ) {
        std::vector<void**> tablesCopy;
        {
            std::shared_lock<std::shared_mutex> readLock(registryMutex_);
            tablesCopy.reserve(contextTables_.size());
            for (const OrigContextVTable& entryItem : contextTables_) {
                if (entryItem.vtablePtr) tablesCopy.push_back(entryItem.vtablePtr);
            }
        }
        for (void** tblPtr : tablesCopy) {
            InstallOrUpdateContext(
                tblPtr, hookPs, hookDrawIdx, hookDraw,
                hookDrawIdxInst, hookDrawInst, hookDrawIdxInd, hookDrawInd,
                hookClear, forceForeignRehook, hookExecCmd, hookFlush
            );
        }
    }

    std::string DescribeTrackedContexts() {
        std::shared_lock<std::shared_mutex> readLock(registryMutex_);
        std::string summaryStr = "ctables=" + std::to_string(contextTables_.size());
        for (size_t idx = 0; idx < contextTables_.size() && idx < 6; ++idx) {
            void** tbl = contextTables_[idx].vtablePtr;
            if (!tbl) continue;
            summaryStr += " [" + std::to_string(idx) + ":ps=" + DescribeCodeModule(tbl[9]) +
                          ",di=" + DescribeCodeModule(tbl[12]) +
                          ",dr=" + DescribeCodeModule(tbl[13]) +
                          ",dii=" + DescribeCodeModule(tbl[20]) + "]";
        }
        return summaryStr;
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
        FnGetImmediateContext hookGetImm,
        bool isDevice1 = false,
        FnGetImmediateContext1 hookGetImm1 = nullptr,
        FnCreateDeferredContext1 hookDefCtx1 = nullptr
    ) {
        if (!devVtbl) return false;
        {
            std::shared_lock<std::shared_mutex> readLock(registryMutex_);
            bool seenTable = false;
            for (const OrigDeviceVTable& item : deviceTables_) {
                if (item.vtablePtr == devVtbl) {
                    seenTable = true;
                    break;
                }
            }
            if (!seenTable) return true;
        }
        if (!d3d11Range_.valid) return true;
        bool needBase = IsRawD3D11Slot(devVtbl[15], reinterpret_cast<const void*>(hookPs)) ||
                        IsRawD3D11Slot(devVtbl[27], reinterpret_cast<const void*>(hookDefCtx)) ||
                        IsRawD3D11Slot(devVtbl[40], reinterpret_cast<const void*>(hookGetImm));
        bool needDev1 = isDevice1 && hookGetImm1 && hookDefCtx1 &&
                        (IsRawD3D11Slot(devVtbl[43], reinterpret_cast<const void*>(hookGetImm1)) ||
                         IsRawD3D11Slot(devVtbl[44], reinterpret_cast<const void*>(hookDefCtx1)));
        return needBase || needDev1;
    }

    bool ShouldSyncContextVTable(
        void** ctxVtbl,
        FnPSSetShader hookPs,
        FnDrawIndexed hookDrawIdx,
        FnDraw hookDraw,
        FnDrawIndexedInstanced hookDrawIdxInst,
        FnDrawInstanced hookDrawInst,
        FnDrawIndexedInstancedIndirect hookDrawIdxInd,
        FnDrawInstancedIndirect hookDrawInd,
        FnClearState hookClear,
        FnExecuteCommandList hookExecCmd = nullptr,
        FnFlush hookFlush = nullptr
    ) {
        if (!ctxVtbl) return false;
        {
            std::shared_lock<std::shared_mutex> readLock(registryMutex_);
            bool seenTable = false;
            for (const OrigContextVTable& item : contextTables_) {
                if (item.vtablePtr == ctxVtbl) {
                    seenTable = true;
                    break;
                }
            }
            if (!seenTable) return true;
        }
        if (!d3d11Range_.valid) return true;
        return IsRawD3D11Slot(ctxVtbl[9], reinterpret_cast<const void*>(hookPs)) ||
               IsRawD3D11Slot(ctxVtbl[12], reinterpret_cast<const void*>(hookDrawIdx)) ||
               IsRawD3D11Slot(ctxVtbl[13], reinterpret_cast<const void*>(hookDraw)) ||
               IsRawD3D11Slot(ctxVtbl[20], reinterpret_cast<const void*>(hookDrawIdxInst)) ||
               IsRawD3D11Slot(ctxVtbl[21], reinterpret_cast<const void*>(hookDrawInst)) ||
               IsRawD3D11Slot(ctxVtbl[39], reinterpret_cast<const void*>(hookDrawIdxInd)) ||
               IsRawD3D11Slot(ctxVtbl[40], reinterpret_cast<const void*>(hookDrawInd)) ||
               (hookExecCmd && IsRawD3D11Slot(ctxVtbl[55], reinterpret_cast<const void*>(hookExecCmd))) ||
               IsRawD3D11Slot(ctxVtbl[110], reinterpret_cast<const void*>(hookClear)) ||
               (hookFlush && IsRawD3D11Slot(ctxVtbl[111], reinterpret_cast<const void*>(hookFlush)));
    }

    uint32_t NeedsFastContextResync(
        void** ctxVtbl,
        FnPSSetShader hookPs,
        FnDrawIndexed hookDrawIdx,
        FnDraw hookDraw,
        FnDrawIndexedInstanced hookDrawIdxInst,
        FnDrawInstanced hookDrawInst,
        FnDrawIndexedInstancedIndirect hookDrawIdxInd,
        FnDrawInstancedIndirect hookDrawInd,
        FnClearState hookClear,
        FnExecuteCommandList hookExecCmd = nullptr,
        FnFlush hookFlush = nullptr
    ) const {
        if (!ctxVtbl || !d3d11Range_.valid) return 0u;
        uint32_t slotMask = 0u;
        if (IsRawD3D11Slot(ctxVtbl[9], reinterpret_cast<const void*>(hookPs))) slotMask |= (1u << 0);
        if (IsRawD3D11Slot(ctxVtbl[12], reinterpret_cast<const void*>(hookDrawIdx))) slotMask |= (1u << 1);
        if (IsRawD3D11Slot(ctxVtbl[13], reinterpret_cast<const void*>(hookDraw))) slotMask |= (1u << 2);
        if (IsRawD3D11Slot(ctxVtbl[20], reinterpret_cast<const void*>(hookDrawIdxInst))) slotMask |= (1u << 3);
        if (IsRawD3D11Slot(ctxVtbl[21], reinterpret_cast<const void*>(hookDrawInst))) slotMask |= (1u << 4);
        if (IsRawD3D11Slot(ctxVtbl[39], reinterpret_cast<const void*>(hookDrawIdxInd))) slotMask |= (1u << 5);
        if (IsRawD3D11Slot(ctxVtbl[40], reinterpret_cast<const void*>(hookDrawInd))) slotMask |= (1u << 6);
        if (hookExecCmd && IsRawD3D11Slot(ctxVtbl[55], reinterpret_cast<const void*>(hookExecCmd))) slotMask |= (1u << 7);
        if (IsRawD3D11Slot(ctxVtbl[110], reinterpret_cast<const void*>(hookClear))) slotMask |= (1u << 8);
        if (hookFlush && IsRawD3D11Slot(ctxVtbl[111], reinterpret_cast<const void*>(hookFlush))) slotMask |= (1u << 9);
        return slotMask;
    }

    bool IsRawD3D11CodePtr(const void* ptrVal) {
        if (!ptrVal) return false;
        if (!d3d11Range_.valid) {
            std::unique_lock<std::shared_mutex> writeLock(registryMutex_);
            EnsureRangesLoaded();
        }
        return d3d11Range_.Contains(ptrVal);
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
