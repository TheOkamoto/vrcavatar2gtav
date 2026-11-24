/*
 * gtav_vtoon.cpp
 * ==============
 * Layer 4b (ASI Entrypoint, Factory/Present Interception & D3D11 Dispatcher):
 * Uses `vtoon_detour.hpp` to hook `D3D11CreateDevice*`, COM VTables across
 * `ID3D11Device`, Immediate/Deferred `ID3D11DeviceContext`s, and `IDXGISwapChain`,
 * plus `ScriptHookV`'s present callback for overlay-safe frame resets and F10 reload.
 */

#include "vtoon_detour.hpp"

#include <atomic>
#include <unordered_map>

namespace {

struct ContextDrawState {
    gtav_vtoon::ShaderClassification shaderClass{};
    ID3D11Buffer* cbGlobal = nullptr;
    ID3D11Buffer* cbDraw = nullptr;
};

static constexpr size_t kFastContextSlotCount = 64;
std::atomic<ID3D11DeviceContext*> gFastContextOwners[kFastContextSlotCount]{};
ContextDrawState gFastContextStates[kFastContextSlotCount]{};

struct CapturedPedDrawState {
    ID3D11RenderTargetView* rtvs[8] = {};
    UINT numRtvs = 0;
    ID3D11DepthStencilView* dsv = nullptr;
    ID3D11PixelShader* psShader = nullptr;
    ID3D11ClassInstance* psInst[8] = {};
    UINT psInstCount = 8;
    ID3D11Buffer* psCb7 = nullptr;
    ID3D11Buffer* psCb9 = nullptr;
    ID3D11ShaderResourceView* psSrv17 = nullptr;
    ID3D11ShaderResourceView* psSrv18 = nullptr;
    ID3D11SamplerState* psSamp13 = nullptr;
    ID3D11RasterizerState* rastState = nullptr;
};

std::atomic<bool> gHooksInstalled{false};
std::atomic<bool> gShuttingDown{false};
std::atomic<bool> gShadersBootstrapped{false};
std::atomic<bool> gPrevF10Down{false};
std::atomic<bool> gLoggedLiveDevice{false};
std::atomic<bool> gLoggedScriptHookPresent{false};
std::atomic<bool> gLoggedFirstCreatePs{false};
std::atomic<bool> gLoggedFirstFrameBoundary{false};
std::atomic<bool> gPrimaryDeviceBound{false};
std::atomic<bool> gHookPresentSawFrame{false};
std::atomic<bool> gScriptHookCallbackRegistered{false};
std::atomic<ID3D11Device*> gPrimaryGameDevice{nullptr};
HANDLE gBootstrapThread = nullptr;

std::mutex gContextStateMutex;
std::unordered_map<ID3D11DeviceContext*, ContextDrawState*> gOverflowContextMap;
gtav_vtoon::VTableRegistry gVTableRegistry;

gtav_vtoon::D3D11DetourRecord gCreateDeviceDetour{};
gtav_vtoon::D3D11DetourRecord gCreateDeviceSwapDetour{};
gtav_vtoon::FnD3D11CreateDevice gOrigD3D11CreateDevice = nullptr;
gtav_vtoon::FnD3D11CreateDeviceAndSwapChain gOrigD3D11CreateDeviceAndSwapChain = nullptr;

ContextDrawState* AcquireContextState(ID3D11DeviceContext* d3dCtx) {
    const size_t startIdx = (reinterpret_cast<uintptr_t>(d3dCtx) >> 5) & (kFastContextSlotCount - 1);
    for (size_t stepIdx = 0; stepIdx < kFastContextSlotCount; ++stepIdx) {
        const size_t slotIdx = (startIdx + stepIdx) & (kFastContextSlotCount - 1);
        ID3D11DeviceContext* curOwner = gFastContextOwners[slotIdx].load(std::memory_order_acquire);
        if (curOwner == d3dCtx) {
            return &gFastContextStates[slotIdx];
        }
        if (curOwner == nullptr) {
            ID3D11DeviceContext* expectedNull = nullptr;
            if (gFastContextOwners[slotIdx].compare_exchange_strong(
                    expectedNull, d3dCtx, std::memory_order_acq_rel, std::memory_order_acquire)) {
                return &gFastContextStates[slotIdx];
            }
            if (gFastContextOwners[slotIdx].load(std::memory_order_acquire) == d3dCtx) {
                return &gFastContextStates[slotIdx];
            }
        }
    }

    std::lock_guard<std::mutex> lockGuard(gContextStateMutex);
    auto foundIter = gOverflowContextMap.find(d3dCtx);
    if (foundIter != gOverflowContextMap.end()) {
        return foundIter->second;
    }
    ContextDrawState* freshState = new ContextDrawState{};
    gOverflowContextMap[d3dCtx] = freshState;
    return freshState;
}

void ReleaseAllContextStates() {
    for (size_t slotIdx = 0; slotIdx < kFastContextSlotCount; ++slotIdx) {
        if (gFastContextStates[slotIdx].cbGlobal) {
            gFastContextStates[slotIdx].cbGlobal->Release();
            gFastContextStates[slotIdx].cbGlobal = nullptr;
        }
        if (gFastContextStates[slotIdx].cbDraw) {
            gFastContextStates[slotIdx].cbDraw->Release();
            gFastContextStates[slotIdx].cbDraw = nullptr;
        }
        gFastContextStates[slotIdx].shaderClass = {};
        gFastContextOwners[slotIdx].store(nullptr, std::memory_order_release);
    }
    std::lock_guard<std::mutex> lockGuard(gContextStateMutex);
    for (auto& pairItem : gOverflowContextMap) {
        ContextDrawState* statePtr = pairItem.second;
        if (!statePtr) continue;
        if (statePtr->cbGlobal) statePtr->cbGlobal->Release();
        if (statePtr->cbDraw) statePtr->cbDraw->Release();
        delete statePtr;
    }
    gOverflowContextMap.clear();
}

void CaptureBeforePedOverride(ID3D11DeviceContext* d3dCtx, CapturedPedDrawState& capState) {
    d3dCtx->OMGetRenderTargets(8, capState.rtvs, &capState.dsv);
    capState.numRtvs = 0;
    for (UINT idx = 0; idx < 8; ++idx) {
        if (capState.rtvs[idx] != nullptr) {
            capState.numRtvs = idx + 1;
        }
    }
    d3dCtx->PSGetShader(&capState.psShader, capState.psInst, &capState.psInstCount);
    d3dCtx->PSGetConstantBuffers(7, 1, &capState.psCb7);
    d3dCtx->PSGetConstantBuffers(9, 1, &capState.psCb9);
    ID3D11ShaderResourceView* srvs[2] = {};
    d3dCtx->PSGetShaderResources(17, 2, srvs);
    capState.psSrv17 = srvs[0];
    capState.psSrv18 = srvs[1];
    d3dCtx->PSGetSamplers(13, 1, &capState.psSamp13);
    d3dCtx->RSGetState(&capState.rastState);
}

void RestoreAfterPedOverride(
    ID3D11DeviceContext* d3dCtx,
    gtav_vtoon::GtaShaderKind shaderKind,
    CapturedPedDrawState& capState,
    bool didOverride
) {
    if (didOverride) {
        if (shaderKind != gtav_vtoon::GtaShaderKind::PedForwardAlpha) {
            d3dCtx->OMSetRenderTargets(capState.numRtvs, capState.rtvs, capState.dsv);
        }
        d3dCtx->PSSetShader(capState.psShader, capState.psInst, capState.psInstCount);
        d3dCtx->PSSetConstantBuffers(7, 1, &capState.psCb7);
        d3dCtx->PSSetConstantBuffers(9, 1, &capState.psCb9);
        ID3D11ShaderResourceView* srvs[2] = {capState.psSrv17, capState.psSrv18};
        d3dCtx->PSSetShaderResources(17, 2, srvs);
        d3dCtx->PSSetSamplers(13, 1, &capState.psSamp13);
        d3dCtx->RSSetState(capState.rastState);
    }

    for (UINT idx = 0; idx < 8; ++idx) {
        if (capState.rtvs[idx]) capState.rtvs[idx]->Release();
        if (idx < capState.psInstCount && capState.psInst[idx]) capState.psInst[idx]->Release();
    }
    if (capState.dsv) capState.dsv->Release();
    if (capState.psShader) capState.psShader->Release();
    if (capState.psCb7) capState.psCb7->Release();
    if (capState.psCb9) capState.psCb9->Release();
    if (capState.psSrv17) capState.psSrv17->Release();
    if (capState.psSrv18) capState.psSrv18->Release();
    if (capState.psSamp13) capState.psSamp13->Release();
    if (capState.rastState) capState.rastState->Release();
}

void EnsureShadersCompiledFromDevice(ID3D11Device* gameDev) {
    if (gShadersBootstrapped.load(std::memory_order_acquire) || !gameDev) {
        return;
    }
    if (gtav_vtoon::VToonHookEngine::Instance().CompileAllVToonShaders(gameDev)) {
        gShadersBootstrapped.store(true, std::memory_order_release);
    }
}

void EnsureShadersCompiledFromContext(ID3D11DeviceContext* d3dCtx) {
    if (gShadersBootstrapped.load(std::memory_order_acquire) || !d3dCtx ||
        d3dCtx->GetType() != D3D11_DEVICE_CONTEXT_IMMEDIATE) {
        return;
    }
    ID3D11Device* gameDev = nullptr;
    d3dCtx->GetDevice(&gameDev);
    if (!gameDev) {
        return;
    }
    EnsureShadersCompiledFromDevice(gameDev);
    gameDev->Release();
}

template <typename FnInvokeOrig>
void DispatchTrackedDraw(ID3D11DeviceContext* d3dCtx, FnInvokeOrig&& invokeOrig) {
    if (!gHooksInstalled.load(std::memory_order_acquire) || gtav_vtoon::gVToonBypassDrawHook) {
        invokeOrig();
        return;
    }

    gtav_vtoon::VToonHookEngine& engine = gtav_vtoon::VToonHookEngine::Instance();
    if (!engine.IsEnabled()) {
        invokeOrig();
        return;
    }

    EnsureShadersCompiledFromContext(d3dCtx);

    ContextDrawState* ctxState = AcquireContextState(d3dCtx);
    const gtav_vtoon::ShaderClassification shaderClass = ctxState->shaderClass;
    const gtav_vtoon::GtaShaderKind kind = shaderClass.kind;

    if (kind == gtav_vtoon::GtaShaderKind::None) {
        invokeOrig();
        return;
    }

    const bool isImmediate = (d3dCtx->GetType() == D3D11_DEVICE_CONTEXT_IMMEDIATE);
    if (kind == gtav_vtoon::GtaShaderKind::DirectionalLighting ||
        kind == gtav_vtoon::GtaShaderKind::DirectionalLightingMsaa) {
        if (!isImmediate) {
            invokeOrig();
            return;
        }
        if (!ctxState->cbGlobal || !ctxState->cbDraw) {
            engine.CreateContextConstantBuffers(&ctxState->cbGlobal, &ctxState->cbDraw);
        }
        gtav_vtoon::ScopedDrawHookBypass bypassGuard;
        engine.ExecuteDirectionalWithOverlay(d3dCtx, shaderClass, ctxState->cbGlobal, invokeOrig);
        return;
    }

    engine.LogFirstTrackedPedDraw();
    ID3D11ShaderResourceView* curSrv0 = nullptr;
    {
        gtav_vtoon::ScopedDrawHookBypass srvQueryGuard;
        d3dCtx->PSGetShaderResources(0, 1, &curSrv0);
    }
    int resolvedCharId = 0;
    if (curSrv0) {
        bool isProbePending = false;
        resolvedCharId = engine.IdentifyTextureCharId(d3dCtx, curSrv0, isProbePending);
        curSrv0->Release();
    }
    if (resolvedCharId <= 0) {
        invokeOrig();
        return;
    }

    if (!ctxState->cbGlobal || !ctxState->cbDraw) {
        engine.CreateContextConstantBuffers(&ctxState->cbGlobal, &ctxState->cbDraw);
    }

    CapturedPedDrawState capState{};
    CaptureBeforePedOverride(d3dCtx, capState);

    bool needsRestore = false;
    {
        gtav_vtoon::ScopedDrawHookBypass bypassGuard;
        engine.PreparePedDrawOverride(
            d3dCtx,
            kind,
            resolvedCharId,
            capState.rtvs,
            capState.numRtvs,
            capState.dsv,
            ctxState->cbGlobal,
            ctxState->cbDraw,
            needsRestore
        );
        invokeOrig();
        RestoreAfterPedOverride(d3dCtx, kind, capState, needsRestore);
    }
}

void InstallDeviceVTableHooks(ID3D11Device* d3dDevice);
void InstallContextVTableHooks(ID3D11DeviceContext* d3dCtx);
void InstallSwapChainVTableHooks(IDXGISwapChain* swapChain);

HRESULT STDMETHODCALLTYPE HookCreatePixelShader(
    ID3D11Device* d3dDevice,
    const void* bytecodePtr,
    SIZE_T bytecodeLen,
    ID3D11ClassLinkage* classLinkage,
    ID3D11PixelShader** outPixelShader
) {
    gtav_vtoon::OrigDeviceVTable origTable = gVTableRegistry.FindDevice(*reinterpret_cast<void***>(d3dDevice));
    if (!origTable.origCreatePixelShader) {
        return E_FAIL;
    }
    HRESULT createRes = origTable.origCreatePixelShader(
        d3dDevice, bytecodePtr, bytecodeLen, classLinkage, outPixelShader);
    ID3D11Device* primaryDev = gPrimaryGameDevice.load(std::memory_order_acquire);
    if (!gShuttingDown.load(std::memory_order_acquire) && SUCCEEDED(createRes) &&
        outPixelShader && *outPixelShader && (!primaryDev || primaryDev == d3dDevice)) {
        if (!gLoggedFirstCreatePs.exchange(true)) {
            gtav_vtoon::LogVToonMessage("Intercepted first live CreatePixelShader call");
        }
        gtav_vtoon::VToonHookEngine::Instance().RegisterPixelShader(
            *outPixelShader, bytecodePtr, bytecodeLen);
    }
    return createRes;
}

HRESULT STDMETHODCALLTYPE HookCreateDeferredContext(
    ID3D11Device* d3dDevice,
    UINT contextFlags,
    ID3D11DeviceContext** outDeferredCtx
) {
    gtav_vtoon::OrigDeviceVTable origTable = gVTableRegistry.FindDevice(*reinterpret_cast<void***>(d3dDevice));
    if (!origTable.origCreateDeferredContext) {
        return E_FAIL;
    }
    HRESULT createRes = origTable.origCreateDeferredContext(d3dDevice, contextFlags, outDeferredCtx);
    ID3D11Device* primaryDev = gPrimaryGameDevice.load(std::memory_order_acquire);
    if (!gShuttingDown.load(std::memory_order_acquire) && SUCCEEDED(createRes) &&
        outDeferredCtx && *outDeferredCtx && (!primaryDev || primaryDev == d3dDevice)) {
        static std::atomic<bool> loggedDeferredHook{false};
        if (!loggedDeferredHook.exchange(true)) {
            gtav_vtoon::LogVToonMessage("Hooked live ID3D11DeviceContext deferred context");
        }
        ContextDrawState* ctxState = AcquireContextState(*outDeferredCtx);
        ctxState->shaderClass = {};
        InstallContextVTableHooks(*outDeferredCtx);
    }
    return createRes;
}

void STDMETHODCALLTYPE HookGetImmediateContext(
    ID3D11Device* d3dDevice,
    ID3D11DeviceContext** outImmCtx
) {
    gtav_vtoon::OrigDeviceVTable origTable = gVTableRegistry.FindDevice(*reinterpret_cast<void***>(d3dDevice));
    if (!origTable.origGetImmediateContext) {
        return;
    }
    origTable.origGetImmediateContext(d3dDevice, outImmCtx);
    ID3D11Device* primaryDev = gPrimaryGameDevice.load(std::memory_order_acquire);
    if (!gShuttingDown.load(std::memory_order_acquire) && outImmCtx && *outImmCtx &&
        (!primaryDev || primaryDev == d3dDevice)) {
        InstallContextVTableHooks(*outImmCtx);
    }
}

void STDMETHODCALLTYPE HookPSSetShader(
    ID3D11DeviceContext* d3dCtx,
    ID3D11PixelShader* pixelShader,
    ID3D11ClassInstance* const* classInstances,
    UINT numClassInstances
) {
    gtav_vtoon::OrigContextVTable origTable = gVTableRegistry.FindContext(*reinterpret_cast<void***>(d3dCtx));
    if (!origTable.origPSSetShader) {
        return;
    }
    origTable.origPSSetShader(d3dCtx, pixelShader, classInstances, numClassInstances);
    if (!gHooksInstalled.load(std::memory_order_acquire) || gtav_vtoon::gVToonBypassDrawHook) {
        return;
    }
    ContextDrawState* ctxState = AcquireContextState(d3dCtx);
    ctxState->shaderClass = pixelShader
                                ? gtav_vtoon::VToonHookEngine::Instance().LookupShader(pixelShader)
                                : gtav_vtoon::ShaderClassification{};
}

void STDMETHODCALLTYPE HookClearState(ID3D11DeviceContext* d3dCtx) {
    gtav_vtoon::OrigContextVTable origTable = gVTableRegistry.FindContext(*reinterpret_cast<void***>(d3dCtx));
    if (!origTable.origClearState) {
        return;
    }
    origTable.origClearState(d3dCtx);
    if (!gHooksInstalled.load(std::memory_order_acquire)) {
        return;
    }
    ContextDrawState* ctxState = AcquireContextState(d3dCtx);
    ctxState->shaderClass = {};
}

void STDMETHODCALLTYPE HookDrawIndexed(
    ID3D11DeviceContext* d3dCtx,
    UINT indexCount,
    UINT startIndexLocation,
    INT baseVertexLocation
) {
    gtav_vtoon::OrigContextVTable origTable = gVTableRegistry.FindContext(*reinterpret_cast<void***>(d3dCtx));
    if (!origTable.origDrawIndexed) return;
    DispatchTrackedDraw(d3dCtx, [&]() {
        origTable.origDrawIndexed(d3dCtx, indexCount, startIndexLocation, baseVertexLocation);
    });
}

void STDMETHODCALLTYPE HookDraw(
    ID3D11DeviceContext* d3dCtx,
    UINT vertexCount,
    UINT startVertexLocation
) {
    gtav_vtoon::OrigContextVTable origTable = gVTableRegistry.FindContext(*reinterpret_cast<void***>(d3dCtx));
    if (!origTable.origDraw) return;
    DispatchTrackedDraw(d3dCtx, [&]() {
        origTable.origDraw(d3dCtx, vertexCount, startVertexLocation);
    });
}

void STDMETHODCALLTYPE HookDrawInstanced(
    ID3D11DeviceContext* d3dCtx,
    UINT vertexCountPerInstance,
    UINT instanceCount,
    UINT startVertexLocation,
    UINT startInstanceLocation
) {
    gtav_vtoon::OrigContextVTable origTable = gVTableRegistry.FindContext(*reinterpret_cast<void***>(d3dCtx));
    if (!origTable.origDrawInstanced) return;
    DispatchTrackedDraw(d3dCtx, [&]() {
        origTable.origDrawInstanced(
            d3dCtx, vertexCountPerInstance, instanceCount, startVertexLocation, startInstanceLocation);
    });
}

void STDMETHODCALLTYPE HookDrawIndexedInstanced(
    ID3D11DeviceContext* d3dCtx,
    UINT indexCountPerInstance,
    UINT instanceCount,
    UINT startIndexLocation,
    INT baseVertexLocation,
    UINT startInstanceLocation
) {
    gtav_vtoon::OrigContextVTable origTable = gVTableRegistry.FindContext(*reinterpret_cast<void***>(d3dCtx));
    if (!origTable.origDrawIndexedInstanced) return;
    DispatchTrackedDraw(d3dCtx, [&]() {
        origTable.origDrawIndexedInstanced(
            d3dCtx,
            indexCountPerInstance,
            instanceCount,
            startIndexLocation,
            baseVertexLocation,
            startInstanceLocation
        );
    });
}

void ProcessFrameBoundary(IDXGISwapChain* swapChain) {
    if (!swapChain || !gHooksInstalled.load(std::memory_order_acquire)) {
        return;
    }
    if (!gLoggedFirstFrameBoundary.exchange(true)) {
        gtav_vtoon::LogVToonMessage("Entered first VToon frame boundary");
    }
    gtav_vtoon::VToonHookEngine& engine = gtav_vtoon::VToonHookEngine::Instance();
    const bool needPrimaryBind = !gPrimaryDeviceBound.load(std::memory_order_acquire);
    const bool needFrameReset = engine.NeedsEndFrameReset();

    ID3D11Device* gameDev = nullptr;
    ID3D11DeviceContext* immCtx = nullptr;
    if (SUCCEEDED(swapChain->GetDevice(__uuidof(ID3D11Device), reinterpret_cast<void**>(&gameDev))) && gameDev) {
        if (needPrimaryBind && !gPrimaryDeviceBound.exchange(true, std::memory_order_acq_rel)) {
            gPrimaryGameDevice.store(gameDev, std::memory_order_release);
            InstallDeviceVTableHooks(gameDev);
            EnsureShadersCompiledFromDevice(gameDev);
            gtav_vtoon::LogVToonMessage("Bound primary GTA V D3D11 device via swap chain");
        } else {
            InstallDeviceVTableHooks(gameDev);
        }
        gameDev->GetImmediateContext(&immCtx);
        if (immCtx) {
            InstallContextVTableHooks(immCtx);
        }
        gameDev->Release();
    }
    if (immCtx) {
        if (needFrameReset) {
            gtav_vtoon::ScopedDrawHookBypass bypassGuard;
            engine.EndFrameResetWithContext(immCtx);
        } else {
            engine.EndFrameResetWithContext(nullptr);
        }
        immCtx->Release();
    } else {
        engine.EndFrameResetWithContext(nullptr);
    }

    bool f10Down = (GetAsyncKeyState(VK_F10) & 0x8000) != 0;
    bool prevDown = gPrevF10Down.exchange(f10Down, std::memory_order_acq_rel);
    if (f10Down && !prevDown) {
        engine.ReloadConfigIfRequested(true);
    }
}

HRESULT STDMETHODCALLTYPE HookPresent(IDXGISwapChain* swapChain, UINT syncInterval, UINT flags) {
    if (gHooksInstalled.load(std::memory_order_acquire)) {
        gHookPresentSawFrame.store(true, std::memory_order_release);
        ProcessFrameBoundary(swapChain);
    }
    gtav_vtoon::OrigSwapVTable origTable = gVTableRegistry.FindSwap(*reinterpret_cast<void***>(swapChain));
    return origTable.origPresent ? origTable.origPresent(swapChain, syncInterval, flags) : DXGI_ERROR_INVALID_CALL;
}

void OnScriptHookVPresent(void* swapPtr) {
    if (!gHooksInstalled.load(std::memory_order_acquire) || !swapPtr) {
        return;
    }
    IDXGISwapChain* swapChain = static_cast<IDXGISwapChain*>(swapPtr);
    if (!gLoggedScriptHookPresent.exchange(true)) {
        gtav_vtoon::LogVToonMessage("Captured live IDXGISwapChain via ScriptHookV present callback");
    }
    if (!gHookPresentSawFrame.exchange(false, std::memory_order_acq_rel)) {
        ProcessFrameBoundary(swapChain);
    }
}

void InstallDeviceVTableHooks(ID3D11Device* d3dDevice) {
    if (!d3dDevice) return;
    void** devVtbl = *reinterpret_cast<void***>(d3dDevice);
    if (!gVTableRegistry.ShouldSyncDeviceVTable(
            devVtbl, HookCreatePixelShader, HookCreateDeferredContext, HookGetImmediateContext)) {
        return;
    }
    gVTableRegistry.InstallOrUpdateDevice(
        devVtbl,
        HookCreatePixelShader,
        HookCreateDeferredContext,
        HookGetImmediateContext
    );
}

void InstallContextVTableHooks(ID3D11DeviceContext* d3dCtx) {
    if (!d3dCtx) return;
    void** ctxVtbl = *reinterpret_cast<void***>(d3dCtx);
    if (!gVTableRegistry.ShouldSyncContextVTable(
            ctxVtbl, HookPSSetShader, HookDrawIndexed, HookDraw,
            HookDrawIndexedInstanced, HookDrawInstanced, HookClearState)) {
        return;
    }
    gVTableRegistry.InstallOrUpdateContext(
        ctxVtbl,
        HookPSSetShader,
        HookDrawIndexed,
        HookDraw,
        HookDrawIndexedInstanced,
        HookDrawInstanced,
        HookClearState
    );
}

void InstallSwapChainVTableHooks(IDXGISwapChain* swapChain) {
    if (!swapChain || gScriptHookCallbackRegistered.load(std::memory_order_acquire)) {
        return;
    }
    gVTableRegistry.InstallOrUpdateSwap(*reinterpret_cast<void***>(swapChain), HookPresent);
}

void HookLiveD3D11Handles(ID3D11Device* d3dDev, ID3D11DeviceContext* immCtx, IDXGISwapChain* swapChain) {
    ID3D11Device* primaryDev = gPrimaryGameDevice.load(std::memory_order_acquire);
    if (primaryDev && d3dDev && d3dDev != primaryDev) {
        return;
    }
    if (d3dDev) InstallDeviceVTableHooks(d3dDev);
    if (immCtx) {
        InstallContextVTableHooks(immCtx);
    } else if (d3dDev) {
        ID3D11DeviceContext* queriedCtx = nullptr;
        d3dDev->GetImmediateContext(&queriedCtx);
        if (queriedCtx) {
            InstallContextVTableHooks(queriedCtx);
            queriedCtx->Release();
        }
    }
    if (swapChain) InstallSwapChainVTableHooks(swapChain);
    if (d3dDev && !gLoggedLiveDevice.exchange(true)) {
        gtav_vtoon::LogVToonMessage("Hooked live D3D11 device/context via factory detour");
    }
}

HRESULT WINAPI HookD3D11CreateDevice(
    IDXGIAdapter* adapterPtr,
    D3D_DRIVER_TYPE driverType,
    HMODULE softwareMod,
    UINT createFlags,
    const D3D_FEATURE_LEVEL* featureLevels,
    UINT numLevels,
    UINT sdkVersion,
    ID3D11Device** outDevice,
    D3D_FEATURE_LEVEL* outLevel,
    ID3D11DeviceContext** outImmCtx
) {
    HRESULT callHr = gOrigD3D11CreateDevice(
        adapterPtr, driverType, softwareMod, createFlags, featureLevels, numLevels,
        sdkVersion, outDevice, outLevel, outImmCtx);
    if (!gShuttingDown.load(std::memory_order_acquire) && SUCCEEDED(callHr) &&
        driverType != D3D_DRIVER_TYPE_REFERENCE && driverType != D3D_DRIVER_TYPE_NULL) {
        HookLiveD3D11Handles(
            outDevice ? *outDevice : nullptr,
            outImmCtx ? *outImmCtx : nullptr,
            nullptr);
    }
    return callHr;
}

HRESULT WINAPI HookD3D11CreateDeviceAndSwapChain(
    IDXGIAdapter* adapterPtr,
    D3D_DRIVER_TYPE driverType,
    HMODULE softwareMod,
    UINT createFlags,
    const D3D_FEATURE_LEVEL* featureLevels,
    UINT numLevels,
    UINT sdkVersion,
    const DXGI_SWAP_CHAIN_DESC* swapDesc,
    IDXGISwapChain** outSwapChain,
    ID3D11Device** outDevice,
    D3D_FEATURE_LEVEL* outLevel,
    ID3D11DeviceContext** outImmCtx
) {
    HRESULT callHr = gOrigD3D11CreateDeviceAndSwapChain(
        adapterPtr, driverType, softwareMod, createFlags, featureLevels, numLevels,
        sdkVersion, swapDesc, outSwapChain, outDevice, outLevel, outImmCtx);
    if (!gShuttingDown.load(std::memory_order_acquire) && SUCCEEDED(callHr) &&
        driverType != D3D_DRIVER_TYPE_REFERENCE && driverType != D3D_DRIVER_TYPE_NULL) {
        HookLiveD3D11Handles(
            outDevice ? *outDevice : nullptr,
            outImmCtx ? *outImmCtx : nullptr,
            outSwapChain ? *outSwapChain : nullptr);
    }
    return callHr;
}

DWORD WINAPI BootstrapVToonHooksThread(LPVOID) {
    for (int waitIdx = 0; waitIdx < 300; ++waitIdx) {
        if (GetModuleHandleA("d3d11.dll") && GetModuleHandleA("dxgi.dll")) {
            break;
        }
        Sleep(25);
    }

    HMODULE shvMod = GetModuleHandleA("ScriptHookV.dll");
    if (shvMod) {
        FARPROC regProc = GetProcAddress(shvMod, "?presentCallbackRegister@@YAXP6AXPEAX@Z@Z");
        if (regProc) {
            reinterpret_cast<gtav_vtoon::FnPresentCallbackRegister>(regProc)(OnScriptHookVPresent);
            gScriptHookCallbackRegistered.store(true, std::memory_order_release);
        }
    }

    HMODULE d3d11Mod = GetModuleHandleA("d3d11.dll");
    bool devDetourOk = false;
    bool swapDetourOk = false;
    if (d3d11Mod) {
        FARPROC procDev = GetProcAddress(d3d11Mod, "D3D11CreateDevice");
        FARPROC procSwap = GetProcAddress(d3d11Mod, "D3D11CreateDeviceAndSwapChain");
        devDetourOk = gtav_vtoon::InstallFixed15Detour(
            procDev, HookD3D11CreateDevice, gCreateDeviceDetour, gOrigD3D11CreateDevice);
        swapDetourOk = gtav_vtoon::InstallFixed15Detour(
            procSwap, HookD3D11CreateDeviceAndSwapChain, gCreateDeviceSwapDetour, gOrigD3D11CreateDeviceAndSwapChain);
    }

    gHooksInstalled.store(true, std::memory_order_release);
    std::string statusMsg = "Installed D3D11 VToon hooks (detour=";
    statusMsg += (devDetourOk && swapDetourOk) ? "1" : "0";
    statusMsg += ", shv=";
    statusMsg += gScriptHookCallbackRegistered.load() ? "1)" : "0)";
    gtav_vtoon::LogVToonMessage(statusMsg);
    return 0;
}

}  // namespace

BOOL APIENTRY DllMain(HMODULE moduleHandle, DWORD callReason, LPVOID) {
    if (callReason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(moduleHandle);
        gtav_vtoon::ResetVToonLogFile();
        gtav_vtoon::VToonHookEngine::Instance().InitializeConfig();
        gBootstrapThread = CreateThread(nullptr, 0, BootstrapVToonHooksThread, nullptr, 0, nullptr);
    } else if (callReason == DLL_PROCESS_DETACH) {
        gShuttingDown.store(true, std::memory_order_release);
        gHooksInstalled.store(false, std::memory_order_release);
        if (gBootstrapThread) {
            WaitForSingleObject(gBootstrapThread, 500);
            CloseHandle(gBootstrapThread);
            gBootstrapThread = nullptr;
        }
        if (gScriptHookCallbackRegistered.exchange(false)) {
            HMODULE shvMod = GetModuleHandleA("ScriptHookV.dll");
            if (shvMod) {
                FARPROC unregProc = GetProcAddress(shvMod, "?presentCallbackUnregister@@YAXP6AXPEAX@Z@Z");
                if (unregProc) {
                    reinterpret_cast<gtav_vtoon::FnPresentCallbackUnregister>(unregProc)(OnScriptHookVPresent);
                }
            }
        }
        gtav_vtoon::RemoveFixed15Detour(gCreateDeviceDetour);
        gtav_vtoon::RemoveFixed15Detour(gCreateDeviceSwapDetour);
        ReleaseAllContextStates();
    }
    return TRUE;
}
