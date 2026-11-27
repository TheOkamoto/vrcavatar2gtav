#pragma once
/*
 * vtoon_d3d11_hook.hpp
 * ====================
 * Layer 3 (D3D11 VTable Interception, Shader Classification & Deferred Overlay):
 * Intercepts `ID3D11Device::CreatePixelShader` (via D3DReflect), `ID3D11Device::CreateDeferredContext`,
 * and `ID3D11DeviceContext::{PSSetShader, PSSetShaderResources, OMSetRenderTargets,
 * Draw, DrawIndexed, DrawInstanced}` to detect VToon-tagged character draw calls,
 * emit per-pixel `VToonMaskRT` metadata in the GBuffer pass, execute `PS_VToonDirectionalOverlay`
 * immediately after GTA V's directional pass, and override `ped_alpha.sps` forward hair passes.
 */

#include "vtoon_probe.hpp"
#include "vtoon_shaders_hlsl.hpp"

#include <atomic>
#include <shared_mutex>
#include <unordered_map>

namespace gtav_vtoon {

enum class GtaShaderKind {
    None = 0,
    PedGbufDefault = 1,
    PedGbufStandard = 2,
    PedGbufHairCutout = 3,
    PedGbufHairA2C = 4,
    PedForwardAlpha = 5,
    DirectionalLighting = 6,
    DirectionalLightingMsaa = 7,
};

struct ShaderClassification {
    GtaShaderKind kind = GtaShaderKind::None;
    bool hasLightingLocals = false;
    bool hasViewInverse = false;
    bool hasDepthTex = false;
    bool hasShadowTex = false;
    bool hasSpecTex = false;
    bool hasStencilTex = false;
    bool isMsaaGbuf = false;
};

using FnCreatePixelShader = HRESULT(STDMETHODCALLTYPE*)(ID3D11Device*, const void*, SIZE_T, ID3D11ClassLinkage*, ID3D11PixelShader**);
using FnCreateDeferredContext = HRESULT(STDMETHODCALLTYPE*)(ID3D11Device*, UINT, ID3D11DeviceContext**);
using FnPSSetShader = void(STDMETHODCALLTYPE*)(ID3D11DeviceContext*, ID3D11PixelShader*, ID3D11ClassInstance* const*, UINT);
using FnDrawIndexed = void(STDMETHODCALLTYPE*)(ID3D11DeviceContext*, UINT, UINT, INT);
using FnDraw = void(STDMETHODCALLTYPE*)(ID3D11DeviceContext*, UINT, UINT);
using FnDrawInstanced = void(STDMETHODCALLTYPE*)(ID3D11DeviceContext*, UINT, UINT, UINT, UINT);
using FnD3D11CreateDevice = HRESULT(WINAPI*)(IDXGIAdapter*, D3D_DRIVER_TYPE, HMODULE, UINT, const D3D_FEATURE_LEVEL*, UINT, UINT, ID3D11Device**, D3D_FEATURE_LEVEL*, ID3D11DeviceContext**);
using FnD3D11CreateDeviceAndSwapChain = HRESULT(WINAPI*)(IDXGIAdapter*, D3D_DRIVER_TYPE, HMODULE, UINT, const D3D_FEATURE_LEVEL*, UINT, UINT, const DXGI_SWAP_CHAIN_DESC*, IDXGISwapChain**, ID3D11Device**, D3D_FEATURE_LEVEL*, ID3D11DeviceContext**);

/** Runtime state singleton holding compiled VToon shaders, caches, and active hooks. */
class VToonHookEngine {
public:
    static VToonHookEngine& Instance() { static VToonHookEngine instance; return instance; }

    void InitializeConfig() { std::lock_guard<std::mutex> lockGuard(stateMutex_); ReloadConfigUnlocked(); }

    void ReloadConfigIfRequested(bool forceReload = false) {
        std::lock_guard<std::mutex> lockGuard(stateMutex_);
        if (!forceReload) return;
        ReloadConfigUnlocked();
        diagState_.forceLiveDump.store(true, std::memory_order_release);
        for (VToonCharacterProfile& profItem : runtimeConfig_.characters) {
            if (profItem.lutSrv) { profItem.lutSrv->Release(); profItem.lutSrv = nullptr; }
            if (profItem.matcapSrv) { profItem.matcapSrv->Release(); profItem.matcapSrv = nullptr; }
            profItem.texturesAttempted = false;
        }
        LogVToonMessage("Hot-reloaded GTAVVToon.ini (live CB snapshot queued)");
    }

    bool CompileAllVToonShaders(ID3D11Device* d3dDevice) {
        if (!d3dDevice) return false;
        struct CompileScopeGuard {
            std::atomic<bool>& flagRef;
            explicit CompileScopeGuard(std::atomic<bool>& targetFlag) : flagRef(targetFlag) { flagRef.store(true, std::memory_order_release); }
            ~CompileScopeGuard() { flagRef.store(false, std::memory_order_release); }
        };
        std::lock_guard<std::mutex> lockGuard(stateMutex_);
        if (shadersCompiled_.load(std::memory_order_acquire)) return true;
        CompileScopeGuard compileGuard(compilingInternalShaders_);
        ScopedDrawHookBypass drawBypassGuard;
        LogVToonMessage("Compiling VToon HLSL shaders on live device");
        if (immContext_) { immContext_->Release(); immContext_ = nullptr; }
        d3dDevice_ = d3dDevice;
        d3dDevice_->GetImmediateContext(&immContext_);

        auto compilePs = [&](const char* srcMain, const char* entryPt, const char* targetProfile, const D3D_SHADER_MACRO* macros, ID3D11PixelShader** outShader) -> bool {
            ID3DBlob *codeBlob = nullptr, *errBlob = nullptr;
            HRESULT compileRes = D3DCompile(srcMain, std::strlen(srcMain), "vtoon_hlsl", macros, nullptr, entryPt, targetProfile, D3DCOMPILE_OPTIMIZATION_LEVEL3, 0, &codeBlob, &errBlob);
            if (FAILED(compileRes) || !codeBlob) {
                std::string errMsg = errBlob ? std::string(static_cast<const char*>(errBlob->GetBufferPointer()), errBlob->GetBufferSize()) : "unknown";
                LogVToonMessage(std::string("Shader compile failed (") + entryPt + "): " + errMsg);
                if (errBlob) errBlob->Release();
                return false;
            }
            HRESULT createRes = d3dDevice_->CreatePixelShader(codeBlob->GetBufferPointer(), codeBlob->GetBufferSize(), nullptr, outShader);
            codeBlob->Release();
            if (errBlob) errBlob->Release();
            return SUCCEEDED(createRes) && (*outShader != nullptr);
        };

        std::string combinedOverlay = std::string(kVToonCoreEvalHlsl) + "\n" + kVToonDeferredOverlayHlsl;
        std::string combinedForward = std::string(kVToonCoreEvalHlsl) + "\n" + kVToonForwardAlphaHlsl;
        const D3D_SHADER_MACRO a2cMacros[] = {{"VTOON_A2C_MASK", "1"}, {nullptr, nullptr}};
        const D3D_SHADER_MACRO stdMacros[] = {{"VTOON_PED_STD", "1"}, {nullptr, nullptr}};
        const D3D_SHADER_MACRO msaaMacros[] = {{"VTOON_MSAA", "1"}, {nullptr, nullptr}};

        bool allOk = compilePs(kVToonPedGBufferHlsl, "MainPedGBuffer", "ps_4_0", nullptr, &psPedGbuf_);
        allOk &= compilePs(kVToonPedGBufferHlsl, "MainPedGBuffer", "ps_4_0", stdMacros, &psPedGbufStd_);
        allOk &= compilePs(kVToonPedGBufferHlsl, "MainPedGBuffer", "ps_5_0", a2cMacros, &psPedGbufA2C_);
        allOk &= compilePs(combinedOverlay.c_str(), "MainDeferredOverlay", "ps_4_0", nullptr, &psOverlay_);
        allOk &= compilePs(combinedOverlay.c_str(), "MainDeferredOverlay", "ps_5_0", msaaMacros, &psOverlayMsaa_);
        allOk &= compilePs(combinedForward.c_str(), "MainForwardAlpha", "ps_4_0", nullptr, &psForwardAlpha_);

        auto makeDynCb = [&](UINT byteLen, ID3D11Buffer** outBuf) {
            D3D11_BUFFER_DESC cbDesc{byteLen, D3D11_USAGE_DYNAMIC, D3D11_BIND_CONSTANT_BUFFER, D3D11_CPU_ACCESS_WRITE, 0, 0};
            d3dDevice_->CreateBuffer(&cbDesc, nullptr, outBuf);
        };
        makeDynCb(sizeof(VToonGpuGlobalCB), &cbGlobal_);
        makeDynCb(sizeof(VToonDrawCB), &cbDraw_);

        D3D11_SAMPLER_DESC sampDesc{D3D11_FILTER_MIN_MAG_MIP_LINEAR, D3D11_TEXTURE_ADDRESS_CLAMP, D3D11_TEXTURE_ADDRESS_CLAMP, D3D11_TEXTURE_ADDRESS_CLAMP, 0.0f, 1u, D3D11_COMPARISON_NEVER, {0, 0, 0, 0}, 0.0f, D3D11_FLOAT32_MAX};
        d3dDevice_->CreateSamplerState(&sampDesc, &linearClampSamp_);
        D3D11_BLEND_DESC opaqueBlend{};
        opaqueBlend.RenderTarget[0].RenderTargetWriteMask = D3D11_COLOR_WRITE_ENABLE_ALL;
        d3dDevice_->CreateBlendState(&opaqueBlend, &opaqueBlendState_);
        D3D11_RASTERIZER_DESC cullNoneDesc{D3D11_FILL_SOLID, D3D11_CULL_NONE, FALSE, 0, 0.0f, 0.0f, TRUE, FALSE, FALSE, FALSE};
        d3dDevice_->CreateRasterizerState(&cullNoneDesc, &cullNoneRastState_);
        D3D11_DEPTH_STENCIL_DESC depthDisDesc{};
        depthDisDesc.DepthWriteMask = D3D11_DEPTH_WRITE_MASK_ZERO;
        d3dDevice_->CreateDepthStencilState(&depthDisDesc, &depthDisabledState_);

        bool proberReady = watermarkProber_.Initialize(d3dDevice_, opaqueBlendState_, cullNoneRastState_, depthDisabledState_);
        liveDiagDumper_.Initialize(d3dDevice_);
        bool compiledOk = allOk && proberReady && cbGlobal_ && cbDraw_ && opaqueBlendState_ && cullNoneRastState_ && depthDisabledState_;
        shadersCompiled_.store(compiledOk, std::memory_order_release);
        LogVToonMessage(compiledOk ? "Compiled all VToon HLSL shaders successfully" : "Some VToon resources failed");
        return compiledOk;
    }

    void RegisterPixelShader(ID3D11PixelShader* pixelShader, const void* bytecode, SIZE_T bytecodeLen) {
        if (!pixelShader || !bytecode || bytecodeLen < 32 ||
            compilingInternalShaders_.load(std::memory_order_acquire) ||
            gVToonBypassDrawHook) {
            return;
        }
        ID3D11ShaderReflection* shaderRefl = nullptr;
        if (FAILED(D3DReflect(bytecode, bytecodeLen, __uuidof(ID3D11ShaderReflection),
                              reinterpret_cast<void**>(&shaderRefl))) || !shaderRefl) {
            return;
        }
        D3D11_SHADER_DESC shaderDesc{};
        shaderRefl->GetDesc(&shaderDesc);
        ShaderClassification classified{};
        bool hasPedCommon = false;
        bool hasPedMisc = false;
        bool hasLightingGlobals = false;
        bool hasLightingLocals = false;
        bool hasMoreStuff = false;
        bool hasDeferredLight = false;
        bool hasRageMatrices = false;
        bool hasPuddle = false;
        bool hasGbuf0 = false;
        bool hasGbuf1 = false;
        bool hasGbuf3 = false;
        bool hasPedTattoo = false;

        for (UINT cbIdx = 0; cbIdx < shaderDesc.ConstantBuffers; ++cbIdx) {
            ID3D11ShaderReflectionConstantBuffer* cbRef = shaderRefl->GetConstantBufferByIndex(cbIdx);
            D3D11_SHADER_BUFFER_DESC cbDesc{};
            if (FAILED(cbRef->GetDesc(&cbDesc)) || !cbDesc.Name) continue;
            if (std::strcmp(cbDesc.Name, "misc_globals") == 0) {
                if (ID3D11ShaderReflectionVariable* varRef = cbRef->GetVariableByName("globalScalars")) {
                    D3D11_SHADER_VARIABLE_DESC varDesc{};
                    if (SUCCEEDED(varRef->GetDesc(&varDesc))) {
                        int detectedShift = (varDesc.StartOffset >= 192u) ? 1 : 0;
                        miscGlobalsShift_.store(detectedShift, std::memory_order_release);
                        LogMilestoneOnce(1u << 18, "Detected GTA V misc_globals size=" + std::to_string(cbDesc.Size) +
                            " globalScalarsOffset=" + std::to_string(varDesc.StartOffset) + " (shift=" + std::to_string(detectedShift) + ")");
                    }
                }
            }
            if (std::strcmp(cbDesc.Name, "ped_common_shared_locals") == 0) hasPedCommon = true;
            else if (std::strcmp(cbDesc.Name, "pedmisclocals") == 0) hasPedMisc = true;
            else if (std::strcmp(cbDesc.Name, "lighting_globals") == 0) hasLightingGlobals = true;
            else if (std::strcmp(cbDesc.Name, "lighting_locals") == 0) hasLightingLocals = true;
            else if (std::strcmp(cbDesc.Name, "more_stuff") == 0) hasMoreStuff = true;
            else if (std::strcmp(cbDesc.Name, "deferred_lighting_locals") == 0) hasDeferredLight = true;
            else if (std::strcmp(cbDesc.Name, "rage_matrices") == 0) hasRageMatrices = true;
            else if (std::strcmp(cbDesc.Name, "puddle_locals") == 0) hasPuddle = true;
        }
        for (UINT resIdx = 0; resIdx < shaderDesc.BoundResources; ++resIdx) {
            D3D11_SHADER_INPUT_BIND_DESC resDesc{};
            if (FAILED(shaderRefl->GetResourceBindingDesc(resIdx, &resDesc))) continue;
            if (resDesc.Type != D3D_SIT_TEXTURE) continue;
            if (resDesc.BindPoint == 4u) classified.hasShadowTex = true;
            else if (resDesc.BindPoint == 7u) {
                hasGbuf0 = true;
                classified.isMsaaGbuf = (resDesc.Dimension == D3D_SRV_DIMENSION_TEXTURE2DMS);
            } else if (resDesc.BindPoint == 8u) hasGbuf1 = true;
            else if (resDesc.BindPoint == 9u) classified.hasSpecTex = true;
            else if (resDesc.BindPoint == 10u) hasGbuf3 = true;
            else if (resDesc.BindPoint == 11u) classified.hasStencilTex = true;
            else if (resDesc.BindPoint == 12u) classified.hasDepthTex = true;
            else if (resDesc.BindPoint == 14u && resDesc.Dimension == D3D_SRV_DIMENSION_TEXTURE2D) hasPedTattoo = true;
        }

        if (hasPedCommon && shaderDesc.OutputParameters >= 4) {
            if (hasPedMisc && shaderDesc.OutputParameters >= 5) classified.kind = GtaShaderKind::PedGbufHairA2C;
            else if (hasPedMisc) classified.kind = GtaShaderKind::PedGbufHairCutout;
            else if (shaderDesc.InputParameters <= 6) classified.kind = GtaShaderKind::PedGbufDefault;
            else classified.kind = GtaShaderKind::PedGbufStandard;
        } else if (hasPedCommon && shaderDesc.OutputParameters == 1 && shaderDesc.InputParameters >= 6 &&
                   hasLightingGlobals && !hasDeferredLight && !hasPuddle && !hasPedTattoo) {
            classified.kind = GtaShaderKind::PedForwardAlpha;
        } else if (hasLightingGlobals && hasMoreStuff && !hasPedCommon && !hasDeferredLight && !hasPuddle &&
                   hasGbuf0 && hasGbuf1 && hasGbuf3 &&
                   shaderDesc.OutputParameters == 1 && (shaderDesc.InputParameters == 3 || shaderDesc.InputParameters == 4)) {
            classified.kind = (classified.isMsaaGbuf || shaderDesc.InputParameters == 4)
                                  ? GtaShaderKind::DirectionalLightingMsaa
                                  : GtaShaderKind::DirectionalLighting;
            classified.hasLightingLocals = hasLightingLocals;
            classified.hasViewInverse = hasRageMatrices;
        }
        shaderRefl->Release();

        if (classified.kind != GtaShaderKind::None) {
            std::unique_lock<std::shared_mutex> writeLock(shaderMutex_);
            shaderMap_[pixelShader] = classified;
            if (classified.kind == GtaShaderKind::PedGbufStandard ||
                classified.kind == GtaShaderKind::PedGbufHairCutout ||
                classified.kind == GtaShaderKind::PedGbufHairA2C) {
                LogMilestoneOnce(1u << 0, "Registered GTA V Ped GBuffer pixel shaders");
            } else if (classified.kind == GtaShaderKind::DirectionalLighting ||
                       classified.kind == GtaShaderKind::DirectionalLightingMsaa) {
                LogMilestoneOnce(1u << 1, "Registered GTA V DirectionalLighting pixel shader");
            } else if (classified.kind == GtaShaderKind::PedForwardAlpha) {
                LogMilestoneOnce(1u << 13, "Registered GTA V PedForwardAlpha pixel shader");
            }
        }
    }

    ShaderClassification LookupShader(ID3D11PixelShader* pixelShader) {
        if (!pixelShader) return {};
        std::shared_lock<std::shared_mutex> readLock(shaderMutex_);
        auto foundIter = shaderMap_.find(pixelShader);
        return (foundIter != shaderMap_.end()) ? foundIter->second : ShaderClassification{};
    }

    bool CreateContextConstantBuffers(ID3D11Buffer** outGlobalCb, ID3D11Buffer** outDrawCb) {
        std::lock_guard<std::mutex> lockGuard(stateMutex_);
        if (!d3dDevice_ || !outGlobalCb || !outDrawCb) return false;
        auto allocCb = [&](UINT bytes, ID3D11Buffer** dstBuf) {
            if (*dstBuf) return;
            D3D11_BUFFER_DESC desc{bytes, D3D11_USAGE_DYNAMIC, D3D11_BIND_CONSTANT_BUFFER, D3D11_CPU_ACCESS_WRITE, 0, 0};
            d3dDevice_->CreateBuffer(&desc, nullptr, dstBuf);
        };
        allocCb(sizeof(VToonGpuGlobalCB), outGlobalCb);
        allocCb(sizeof(VToonDrawCB), outDrawCb);
        return (*outGlobalCb != nullptr && *outDrawCb != nullptr);
    }

    int IdentifyTextureCharId(ID3D11DeviceContext* d3dCtx, ID3D11ShaderResourceView* diffSrv, bool& outProbePending) {
        outProbePending = false;
        if (!diffSrv || !d3dCtx || !shadersCompiled_.load(std::memory_order_acquire)) return 0;
        D3D11_SHADER_RESOURCE_VIEW_DESC srvDesc{};
        diffSrv->GetDesc(&srvDesc);
        if (srvDesc.ViewDimension != D3D11_SRV_DIMENSION_TEXTURE2D) return 0;
        ID3D11Resource* baseRes = nullptr;
        diffSrv->GetResource(&baseRes);
        if (!baseRes) return 0;
        const uint64_t texSig = ComputeTextureResourceSignature(baseRes);
        {
            std::shared_lock<std::shared_mutex> readLock(texCacheMutex_);
            auto cacheIter = texCharCache_.find(baseRes);
            if (cacheIter != texCharCache_.end() && cacheIter->second.sigHash == texSig) {
                int cachedId = cacheIter->second.charId;
                baseRes->Release();
                outProbePending = (cachedId < 0);
                return (cachedId > 0) ? cachedId : 0;
            }
        }
        if (d3dCtx->GetType() != D3D11_DEVICE_CONTEXT_IMMEDIATE) {
            std::unique_lock<std::shared_mutex> writeLock(texCacheMutex_);
            auto cacheIter = texCharCache_.find(baseRes);
            if (cacheIter != texCharCache_.end() && cacheIter->second.sigHash == texSig) {
                int cachedId = cacheIter->second.charId;
                baseRes->Release();
                outProbePending = (cachedId < 0);
                return (cachedId > 0) ? cachedId : 0;
            }
            if (pendingProbes_.size() < 128) {
                diffSrv->AddRef();
                baseRes->AddRef();
                pendingProbes_.push_back(PendingProbeItem{diffSrv, baseRes, texSig});
                texCharCache_[baseRes] = CachedTexCharEntry{texSig, -1};
                hasPendingProbes_.store(true, std::memory_order_release);
                outProbePending = true;
            }
            baseRes->Release();
            return 0;
        }
        int detectedId = 0;
        { ScopedDrawHookBypass probeBypassGuard; detectedId = watermarkProber_.ProbeTexture(d3dCtx, diffSrv, baseRes); }
        { std::unique_lock<std::shared_mutex> writeLock(texCacheMutex_); texCharCache_[baseRes] = CachedTexCharEntry{texSig, detectedId}; }
        baseRes->Release();
        return detectedId;
    }

    void DrainPendingTextureProbes(ID3D11DeviceContext* immCtx) {
        if (!immCtx || !shadersCompiled_.load(std::memory_order_acquire) ||
            immCtx->GetType() != D3D11_DEVICE_CONTEXT_IMMEDIATE) return;
        std::vector<PendingProbeItem> batchItems;
        {
            std::unique_lock<std::shared_mutex> writeLock(texCacheMutex_);
            hasPendingProbes_.store(false, std::memory_order_release);
            if (pendingProbes_.empty()) return;
            batchItems.swap(pendingProbes_);
        }
        for (PendingProbeItem& item : batchItems) {
            int detectedId = 0;
            { ScopedDrawHookBypass probeBypassGuard; detectedId = watermarkProber_.ProbeTexture(immCtx, item.srvPtr, item.resPtr); }
            { std::unique_lock<std::shared_mutex> writeLock(texCacheMutex_); texCharCache_[item.resPtr] = CachedTexCharEntry{item.sigHash, detectedId}; }
            if (item.srvPtr) item.srvPtr->Release();
            if (item.resPtr) item.resPtr->Release();
        }
    }

    void SetSwapChainSize(UINT widthVal, UINT heightVal) {
        swapWidth_.store(widthVal, std::memory_order_release);
        swapHeight_.store(heightVal, std::memory_order_release);
    }

    bool EnsureMaskTargetMatches(ID3D11Texture2D* gbuf0Tex) {
        if (!gbuf0Tex || !d3dDevice_) return false;
        D3D11_TEXTURE2D_DESC refDesc{};
        gbuf0Tex->GetDesc(&refDesc);
        if (refDesc.Width < 512 || refDesc.Height < 512) return false;
        const UINT targetWidth = swapWidth_.load(std::memory_order_acquire);
        const UINT targetHeight = swapHeight_.load(std::memory_order_acquire);
        if (targetWidth > 0u && targetHeight > 0u &&
            (refDesc.Width != targetWidth || refDesc.Height != targetHeight)) {
            diagState_.skippedGbuf.fetch_add(1u, std::memory_order_relaxed);
            return false;
        }
        if (maskTex_ && maskWidth_ == refDesc.Width && maskHeight_ == refDesc.Height &&
            maskSampleCount_ == refDesc.SampleDesc.Count) return true;
        if (maskSrv_) { maskSrv_->Release(); maskSrv_ = nullptr; }
        if (maskRtv_) { maskRtv_->Release(); maskRtv_ = nullptr; }
        if (maskTex_) { maskTex_->Release(); maskTex_ = nullptr; }

        D3D11_TEXTURE2D_DESC newDesc{refDesc.Width, refDesc.Height, 1, 1, DXGI_FORMAT_R32G32B32A32_FLOAT, refDesc.SampleDesc, D3D11_USAGE_DEFAULT, D3D11_BIND_RENDER_TARGET | D3D11_BIND_SHADER_RESOURCE, 0, 0};
        if (FAILED(d3dDevice_->CreateTexture2D(&newDesc, nullptr, &maskTex_)) || !maskTex_) return false;
        d3dDevice_->CreateRenderTargetView(maskTex_, nullptr, &maskRtv_);
        D3D11_SHADER_RESOURCE_VIEW_DESC srvDesc{};
        srvDesc.Format = newDesc.Format;
        srvDesc.ViewDimension = (refDesc.SampleDesc.Count > 1) ? D3D11_SRV_DIMENSION_TEXTURE2DMS : D3D11_SRV_DIMENSION_TEXTURE2D;
        if (srvDesc.ViewDimension == D3D11_SRV_DIMENSION_TEXTURE2D) srvDesc.Texture2D.MipLevels = 1;
        d3dDevice_->CreateShaderResourceView(maskTex_, &srvDesc, &maskSrv_);
        maskWidth_ = refDesc.Width;
        maskHeight_ = refDesc.Height;
        maskSampleCount_ = refDesc.SampleDesc.Count;
        if (immContext_ && maskRtv_) { const float clrZ[4] = {}; immContext_->ClearRenderTargetView(maskRtv_, clrZ); }
        return (maskRtv_ != nullptr && maskSrv_ != nullptr);
    }

    VToonCharacterProfile* GetCharacterProfile(int charId) {
        for (VToonCharacterProfile& itemProf : runtimeConfig_.characters) {
            if (itemProf.charId == charId) {
                if (!itemProf.texturesAttempted && d3dDevice_) {
                    itemProf.texturesAttempted = true;
                    UINT matcapWidth = 0;
                    itemProf.lutSrv = LoadPngFileToSrv(d3dDevice_, itemProf.lutPngPath, true);
                    itemProf.matcapSrv = LoadPngFileToSrv(d3dDevice_, itemProf.matcapPngPath, false, &matcapWidth);
                    itemProf.matcapIsAtlas = (matcapWidth >= 384u);
                }
                return &itemProf;
            }
        }
        return nullptr;
    }

    void PreparePedDrawOverride(
        ID3D11DeviceContext* d3dCtx, GtaShaderKind kind, int charId, ID3D11RenderTargetView* const* origRtvs,
        UINT numOrigRtvs, ID3D11DepthStencilView* origDsv, ID3D11Buffer* ctxGlobalCb, ID3D11Buffer* ctxDrawCb, bool& outNeedsRestore
    ) {
        outNeedsRestore = false;
        if (!runtimeConfig_.enabled || !shadersCompiled_.load(std::memory_order_acquire) || charId <= 0 || !d3dCtx) return;

        VToonCharacterProfile* charProf = nullptr;
        bool isForwardAlpha = (kind == GtaShaderKind::PedForwardAlpha);
        bool maskReady = false;
        ID3D11RenderTargetView* localMaskRtv = nullptr;
        ID3D11Texture2D* gbuf0Tex = nullptr;
        if (!isForwardAlpha) {
            if (numOrigRtvs < 4 || !origRtvs || !origRtvs[0] || !origRtvs[1] || !origRtvs[2] || !origRtvs[3] || !origDsv) {
                diagState_.skipRtv.fetch_add(1u, std::memory_order_relaxed);
                return;
            }
            ID3D11Resource* gbuf0Res = nullptr;
            origRtvs[0]->GetResource(&gbuf0Res);
            if (!gbuf0Res) return;
            gbuf0Res->QueryInterface(__uuidof(ID3D11Texture2D), reinterpret_cast<void**>(&gbuf0Tex));
            gbuf0Res->Release();
            if (!gbuf0Tex) return;
        }
        {
            std::lock_guard<std::mutex> lockGuard(stateMutex_);
            charProf = GetCharacterProfile(charId);
            if (charProf && !isForwardAlpha && gbuf0Tex) {
                maskReady = EnsureMaskTargetMatches(gbuf0Tex);
                localMaskRtv = maskRtv_;
            }
        }
        if (gbuf0Tex) gbuf0Tex->Release();
        if (!charProf) return;

        ID3D11Buffer* activeGlobalCb = ctxGlobalCb ? ctxGlobalCb : cbGlobal_;
        ID3D11Buffer* activeDrawCb = ctxDrawCb ? ctxDrawCb : cbDraw_;
        if (isForwardAlpha) {
            if (!activeGlobalCb) return;
            ID3D11ShaderResourceView* srvs[2] = {charProf->lutSrv, charProf->matcapSrv};
            ID3D11ShaderResourceView* srv15 = nullptr;
            ID3D11Buffer* cb6Ptr = nullptr;
            d3dCtx->PSGetShaderResources(15, 1, &srv15);
            d3dCtx->PSGetConstantBuffers(6, 1, &cb6Ptr);
            const bool hasCsm = (srv15 != nullptr && cb6Ptr != nullptr);
            if (srv15) srv15->Release();
            if (cb6Ptr) cb6Ptr->Release();
            UploadGlobalConstants(d3dCtx, charId, charProf, true, activeGlobalCb, false, hasCsm, false, false);
            if (d3dCtx->GetType() == D3D11_DEVICE_CONTEXT_IMMEDIATE &&
                diagState_.wantDumpFwd.exchange(false, std::memory_order_acq_rel)) {
                liveDiagDumper_.LogForwardAlphaLive(d3dCtx, charId, miscGlobalsShift_.load(std::memory_order_acquire), hasCsm);
            }
            d3dCtx->PSSetShader(psForwardAlpha_, nullptr, 0);
            d3dCtx->PSSetConstantBuffers(7, 1, &activeGlobalCb);
            d3dCtx->PSSetShaderResources(17, 2, srvs);
            d3dCtx->PSSetSamplers(13, 1, &linearClampSamp_);
            diagState_.fwdAlphaCalls.fetch_add(1u, std::memory_order_relaxed);
            LogMilestoneOnce(1u << 2, "Applied VToon ForwardAlpha ped hair shader override");
            outNeedsRestore = true;
            return;
        }
        if (!maskReady || !localMaskRtv || !activeDrawCb) return;

        if (d3dCtx->GetType() != D3D11_DEVICE_CONTEXT_IMMEDIATE) diagState_.defGbufCalls.fetch_add(1u, std::memory_order_relaxed);
        diagState_.gbufTid.store(GetCurrentThreadId(), std::memory_order_relaxed);
        diagState_.gbufCalls.fetch_add(1u, std::memory_order_relaxed);

        // Synchronous immCtx clear right before Geometry 0 avoids Present() race mid-draw
        if (d3dCtx->GetType() == D3D11_DEVICE_CONTEXT_IMMEDIATE &&
            maskNeedsClearOnNextGbuf_.exchange(false, std::memory_order_acq_rel)) {
            const float clearZero[4] = {0.0f, 0.0f, 0.0f, 0.0f};
            d3dCtx->ClearRenderTargetView(localMaskRtv, clearZero);
            diagState_.RecordFrameGbufStats(frameGbufCount_.exchange(0u, std::memory_order_relaxed));
            charsSeenMask_.store(0u, std::memory_order_release);
            lastOvlDrawSeq_.store(0u, std::memory_order_release);
            if (diagState_.wantDumpGbuf.exchange(false, std::memory_order_acq_rel)) {
                liveDiagDumper_.LogPedGbufLive(d3dCtx, charId, miscGlobalsShift_.load(std::memory_order_acquire), numOrigRtvs);
            }
        }
        frameGbufCount_.fetch_add(1u, std::memory_order_relaxed);
        gbufActiveThisPass_.store(true, std::memory_order_release);
        if (charId > 0 && charId < kMaxVToonCharacters) charsSeenMask_.fetch_or(1u << static_cast<uint32_t>(charId), std::memory_order_acq_rel);

        ID3D11BlendState* origPedBlend = nullptr;
        float pedBlendFactor[4] = {};
        UINT pedSampleMask = 0xFFFFFFFFu;
        d3dCtx->OMGetBlendState(&origPedBlend, pedBlendFactor, &pedSampleMask);
        if (origPedBlend) {
            D3D11_BLEND_DESC pedBlendDesc{};
            origPedBlend->GetDesc(&pedBlendDesc);
            if (pedBlendDesc.IndependentBlendEnable != FALSE && (pedBlendDesc.RenderTarget[4].RenderTargetWriteMask & 0xF) != 0xF) {
                diagState_.indBlend.fetch_add(1u, std::memory_order_relaxed);
                LogMilestoneOnce(1u << 17, "Detected IndependentBlend with masked RT4 writeMask=" +
                    std::to_string(pedBlendDesc.RenderTarget[4].RenderTargetWriteMask));
                if (ID3D11BlendState* unmaskedBlend = GetOrCreateUnmaskedRt4Blend(pedBlendDesc)) {
                    d3dCtx->OMSetBlendState(unmaskedBlend, pedBlendFactor, pedSampleMask);
                }
            }
            origPedBlend->Release();
        }

        ID3D11ShaderResourceView* nullMaskSrv = nullptr;
        d3dCtx->PSSetShaderResources(16, 1, &nullMaskSrv);
        ID3D11RenderTargetView* extendedRtvs[5] = {origRtvs[0], origRtvs[1], origRtvs[2], origRtvs[3], localMaskRtv};
        d3dCtx->OMSetRenderTargets(5, extendedRtvs, origDsv);

        bool isCutout = (kind == GtaShaderKind::PedGbufHairCutout || kind == GtaShaderKind::PedGbufHairA2C);
        UpdateDrawConstantBuffer(d3dCtx, charId, isCutout, charProf, activeDrawCb);
        d3dCtx->PSSetConstantBuffers(9, 1, &activeDrawCb);
        ID3D11PixelShader* chosenPs = (kind == GtaShaderKind::PedGbufHairA2C) ? psPedGbufA2C_ :
            ((kind == GtaShaderKind::PedGbufStandard && psPedGbufStd_) ? psPedGbufStd_ : psPedGbuf_);
        d3dCtx->PSSetShader(chosenPs, nullptr, 0);
        LogMilestoneOnce(1u << 14, "First GBuffer override kind=" + std::to_string(static_cast<int>(kind)) +
            " mask=" + std::to_string(maskWidth_) + "x" + std::to_string(maskHeight_) + " ms=" + std::to_string(maskSampleCount_));
        LogMilestoneOnce(1u << 3, "Applied VToon GBuffer ped override and mask emission");
        outNeedsRestore = true;
    }

    template <typename FnDrawCall>
    void ExecuteDirectionalWithOverlay(
        ID3D11DeviceContext* d3dCtx, const ShaderClassification& dirClass,
        ID3D11Buffer* ctxGlobalCb, uint64_t drawSeq, FnDrawCall&& invokeOriginalDraw
    ) {
        invokeOriginalDraw();
        const uint32_t seenMask = charsSeenMask_.load(std::memory_order_acquire);
        if (!runtimeConfig_.enabled || !shadersCompiled_.load(std::memory_order_acquire) ||
            !gbufActiveThisPass_.load(std::memory_order_acquire) || seenMask == 0u || !maskSrv_ || !d3dCtx) return;
        const bool isMsaaDraw = (dirClass.kind == GtaShaderKind::DirectionalLightingMsaa);
        if ((maskSampleCount_ > 1u) != isMsaaDraw) return;

        auto checkTexDims = [&](ID3D11Resource* baseRes, bool matchSamples) -> bool {
            ID3D11Texture2D* tex2d = nullptr;
            if (!baseRes || FAILED(baseRes->QueryInterface(__uuidof(ID3D11Texture2D), reinterpret_cast<void**>(&tex2d))) || !tex2d) return false;
            D3D11_TEXTURE2D_DESC texDesc{};
            tex2d->GetDesc(&texDesc);
            tex2d->Release();
            return texDesc.Width == maskWidth_ && texDesc.Height == maskHeight_ && (!matchSamples || texDesc.SampleDesc.Count == maskSampleCount_);
        };
        auto doesSrvMatchMask = [&](ID3D11ShaderResourceView* srvPtr) -> bool {
            if (!srvPtr) return false;
            ID3D11Resource* srvRes = nullptr;
            srvPtr->GetResource(&srvRes);
            bool matched = checkTexDims(srvRes, true);
            if (srvRes) srvRes->Release();
            return matched;
        };

        ID3D11RenderTargetView* curRtv = nullptr;
        d3dCtx->OMGetRenderTargets(1, &curRtv, nullptr);
        bool rtMatchesMask = false;
        if (curRtv) {
            ID3D11Resource* rtRes = nullptr;
            curRtv->GetResource(&rtRes);
            curRtv->Release();
            rtMatchesMask = checkTexDims(rtRes, false);
            if (rtRes) rtRes->Release();
        }
        if (!rtMatchesMask) return;

        ID3D11ShaderResourceView *srv4 = nullptr, *gbufSrvs[6] = {};
        d3dCtx->PSGetShaderResources(4, 1, &srv4);
        d3dCtx->PSGetShaderResources(7, 6, gbufSrvs);
        const bool gbufReady = gbufSrvs[0] && gbufSrvs[1] && gbufSrvs[3] && doesSrvMatchMask(gbufSrvs[0]);
        const bool liveDepthOk = dirClass.hasDepthTex && doesSrvMatchMask(gbufSrvs[5]);
        const bool liveShadowOk = dirClass.hasShadowTex && (srv4 != nullptr);
        const bool liveSpecOk = dirClass.hasSpecTex && (gbufSrvs[2] != nullptr);
        const bool liveStencilOk = dirClass.hasStencilTex && (gbufSrvs[4] != nullptr);
        if (srv4) srv4->Release();
        for (int srvIdx = 0; srvIdx < 6; ++srvIdx) if (gbufSrvs[srvIdx]) gbufSrvs[srvIdx]->Release();
        if (!gbufReady) return;

        ID3D11Buffer* activeGlobalCb = ctxGlobalCb ? ctxGlobalCb : cbGlobal_;
        if (!activeGlobalCb) return;

        ID3D11PixelShader* origPs = nullptr;
        ID3D11ClassInstance* origInst[8] = {};
        UINT origInstCount = 8, origSampleMask = 0xFFFFFFFFu;
        d3dCtx->PSGetShader(&origPs, origInst, &origInstCount);
        ID3D11Buffer* origCb7 = nullptr;
        d3dCtx->PSGetConstantBuffers(7, 1, &origCb7);
        ID3D11ShaderResourceView* origExtraSrvs[3] = {};
        d3dCtx->PSGetShaderResources(16, 3, origExtraSrvs);
        ID3D11SamplerState* origSamp13 = nullptr;
        d3dCtx->PSGetSamplers(13, 1, &origSamp13);
        ID3D11BlendState* origBlend = nullptr;
        float origBlendFactor[4] = {};
        d3dCtx->OMGetBlendState(&origBlend, origBlendFactor, &origSampleMask);
        auto releaseCaptured = [&]() {
            if (origBlend) origBlend->Release();
            if (origSamp13) origSamp13->Release();
            for (int srvIdx = 0; srvIdx < 3; ++srvIdx) if (origExtraSrvs[srvIdx]) origExtraSrvs[srvIdx]->Release();
            if (origCb7) origCb7->Release();
            if (origPs) origPs->Release();
            for (UINT idxInst = 0; idxInst < origInstCount; ++idxInst) if (origInst[idxInst]) origInst[idxInst]->Release();
        };
        if (origBlend) {
            D3D11_BLEND_DESC blendDesc{};
            origBlend->GetDesc(&blendDesc);
            if (blendDesc.RenderTarget[0].BlendEnable != FALSE) {
                diagState_.additiveSkip.fetch_add(1u, std::memory_order_relaxed);
                releaseCaptured();
                return;
            }
        }

        const uint64_t prevSeq = lastOvlDrawSeq_.load(std::memory_order_acquire);
        if (prevSeq > 0u && drawSeq > prevSeq) {
            const uint64_t drawGap = drawSeq - prevSeq;
            if (drawGap > 128u) {
                if (maskRtv_ && d3dCtx->GetType() == D3D11_DEVICE_CONTEXT_IMMEDIATE) {
                    const float clearZero[4] = {0.0f, 0.0f, 0.0f, 0.0f};
                    d3dCtx->ClearRenderTargetView(maskRtv_, clearZero);
                }
                gbufActiveThisPass_.store(false, std::memory_order_release);
                maskNeedsClearOnNextGbuf_.store(false, std::memory_order_release);
                charsSeenMask_.store(0u, std::memory_order_release);
                lastOvlDrawSeq_.store(0u, std::memory_order_release);
                releaseCaptured();
                return;
            }
            diagState_.RecordOvlGap(static_cast<uint32_t>(drawGap));
        }

        diagState_.ovlTid.store(GetCurrentThreadId(), std::memory_order_relaxed);
        lastOvlDrawSeq_.store(drawSeq, std::memory_order_release);
        maskNeedsClearOnNextGbuf_.store(true, std::memory_order_release);

        d3dCtx->PSSetShader(isMsaaDraw ? psOverlayMsaa_ : psOverlay_, nullptr, 0);
        d3dCtx->OMSetBlendState(opaqueBlendState_, nullptr, origSampleMask);
        d3dCtx->PSSetSamplers(13, 1, &linearClampSamp_);
        diagState_.overlayCalls.fetch_add(1u, std::memory_order_relaxed);
        if (dirClass.hasLightingLocals) diagState_.ovlSunCalls.fetch_add(1u, std::memory_order_relaxed);
        else diagState_.ovlAmbCalls.fetch_add(1u, std::memory_order_relaxed);

        for (int charId = 1; charId < kMaxVToonCharacters; ++charId) {
            if ((seenMask & (1u << static_cast<uint32_t>(charId))) == 0u) continue;
            VToonCharacterProfile* charProf = nullptr;
            { std::lock_guard<std::mutex> lockGuard(stateMutex_); charProf = GetCharacterProfile(charId); }
            if (!charProf) continue;
            UploadGlobalConstants(d3dCtx, charId, charProf, dirClass.hasLightingLocals, activeGlobalCb, liveDepthOk, liveShadowOk, liveSpecOk, liveStencilOk);
            d3dCtx->PSSetConstantBuffers(7, 1, &activeGlobalCb);
            ID3D11ShaderResourceView* srvs[3] = {maskSrv_, charProf->lutSrv, charProf->matcapSrv};
            d3dCtx->PSSetShaderResources(16, 3, srvs);
            invokeOriginalDraw();
        }
        if (diagState_.wantDumpOvl.exchange(false, std::memory_order_acq_rel)) {
            liveDiagDumper_.LogOverlayLive(d3dCtx, static_cast<int>(dirClass.kind),
                miscGlobalsShift_.load(std::memory_order_acquire), liveDepthOk, liveShadowOk, liveSpecOk, liveStencilOk);
        }
        LogMilestoneOnce(1u << 15, "First overlay diag kind=" + std::to_string(static_cast<int>(dirClass.kind)) +
            " mask=" + std::to_string(maskWidth_) + "x" + std::to_string(maskHeight_) + "x" + std::to_string(maskSampleCount_) +
            " d=" + std::to_string(liveDepthOk ? 1 : 0) + " sh=" + std::to_string(liveShadowOk ? 1 : 0) +
            " sp=" + std::to_string(liveSpecOk ? 1 : 0) + " st=" + std::to_string(liveStencilOk ? 1 : 0));
        LogMilestoneOnce(1u << 11, "Executed VToon deferred directional shading overlay");

        d3dCtx->OMSetBlendState(origBlend, origBlendFactor, origSampleMask);
        d3dCtx->PSSetSamplers(13, 1, &origSamp13);
        d3dCtx->PSSetShaderResources(16, 3, origExtraSrvs);
        d3dCtx->PSSetConstantBuffers(7, 1, &origCb7);
        d3dCtx->PSSetShader(origPs, origInst, origInstCount);
        releaseCaptured();
    }

    void EndFrameResetWithContext(ID3D11DeviceContext* immCtx) {
        if (immCtx && immCtx->GetType() == D3D11_DEVICE_CONTEXT_IMMEDIATE && hasPendingProbes_.load(std::memory_order_acquire)) {
            DrainPendingTextureProbes(immCtx);
        }
        diagState_.OnEndFramePresent(
            miscGlobalsShift_.load(std::memory_order_acquire),
            swapWidth_.load(std::memory_order_relaxed),
            swapHeight_.load(std::memory_order_relaxed));
    }

    bool NeedsEndFrameReset() const {
        return hasPendingProbes_.load(std::memory_order_acquire) || diagState_.NeedsEndFrameDiag();
    }
    bool IsEnabled() const { return configEnabled_.load(std::memory_order_acquire); }
    void RecordVTableRehook(uint32_t patchedMask) { diagState_.RecordVTableRehook(patchedMask); }
    void RecordPostFlushCatch() { diagState_.RecordPostFlushCatch(); }
    void LogFirstTrackedPedDraw() { LogMilestoneOnce(1u << 5, "Intercepted first tracked Ped GBuffer/Forward draw"); }
    void LogMilestoneOnce(uint32_t flagBit, const std::string& msgText) { diagState_.LogMilestoneOnce(flagBit, msgText); }

private:
    ID3D11BlendState* GetOrCreateUnmaskedRt4Blend(const D3D11_BLEND_DESC& srcDesc) {
        if (!d3dDevice_) return nullptr;
        D3D11_BLEND_DESC keyDesc = srcDesc;
        keyDesc.RenderTarget[4].RenderTargetWriteMask = D3D11_COLOR_WRITE_ENABLE_ALL;
        std::lock_guard<std::mutex> lockGuard(stateMutex_);
        for (const auto& cachePair : rt4BlendCache_) {
            if (std::memcmp(&cachePair.first, &keyDesc, sizeof(D3D11_BLEND_DESC)) == 0) return cachePair.second;
        }
        ID3D11BlendState* createdBlend = nullptr;
        if (FAILED(d3dDevice_->CreateBlendState(&keyDesc, &createdBlend)) || !createdBlend) return nullptr;
        rt4BlendCache_.emplace_back(keyDesc, createdBlend);
        return createdBlend;
    }

    void ReloadConfigUnlocked() {
        LoadVToonIniConfig(GetModuleDirectoryA() + "\\GTAVVToon.ini", runtimeConfig_);
        configEnabled_.store(runtimeConfig_.enabled, std::memory_order_release);
    }

    void UpdateDrawConstantBuffer(ID3D11DeviceContext* d3dCtx, int charId, bool isCutout, const VToonCharacterProfile* charProf, ID3D11Buffer* targetDrawCb) {
        D3D11_MAPPED_SUBRESOURCE mapped{};
        if (!targetDrawCb || FAILED(d3dCtx->Map(targetDrawCb, 0, D3D11_MAP_WRITE_DISCARD, 0, &mapped)) || !mapped.pData) return;
        VToonDrawCB* drawPtr = static_cast<VToonDrawCB*>(mapped.pData);
        std::memset(drawPtr, 0, sizeof(VToonDrawCB));
        drawPtr->drawCharInfo[0] = static_cast<float>(charId);
        drawPtr->drawCharInfo[1] = isCutout ? 0.38f : 0.001f;
        drawPtr->drawCharInfo[2] = runtimeConfig_.alphaBoost;
        drawPtr->drawCharInfo[3] = (miscGlobalsShift_.load(std::memory_order_acquire) != 0) ? 1.0f : 0.0f;
        drawPtr->drawTint[0] = drawPtr->drawTint[1] = drawPtr->drawTint[2] = 1.0f;
        drawPtr->drawTint[3] = isCutout ? 1.0f : 0.0f;
        if (charProf && !charProf->slots.empty()) drawPtr->forwardSlot = charProf->slots[0];
        d3dCtx->Unmap(targetDrawCb, 0);
    }

    void UploadGlobalConstants(
        ID3D11DeviceContext* d3dCtx, int charId, const VToonCharacterProfile* charProf, bool hasDirectionalLight,
        ID3D11Buffer* targetGlobalCb, bool hasDepthTex = false, bool hasShadowTex = false, bool hasSpecTex = false, bool hasStencilTex = false
    ) {
        D3D11_MAPPED_SUBRESOURCE mapped{};
        if (!targetGlobalCb || FAILED(d3dCtx->Map(targetGlobalCb, 0, D3D11_MAP_WRITE_DISCARD, 0, &mapped)) || !mapped.pData) return;
        VToonGpuGlobalCB* globPtr = static_cast<VToonGpuGlobalCB*>(mapped.pData);
        std::memset(globPtr, 0, sizeof(VToonGpuGlobalCB));
        globPtr->globalParams0[0] = runtimeConfig_.enabled ? 1.0f : 0.0f; globPtr->globalParams0[1] = runtimeConfig_.daylightScale;
        globPtr->globalParams0[2] = runtimeConfig_.minWorldLum; globPtr->globalParams0[3] = runtimeConfig_.maxWorldLum;
        globPtr->globalParams1[0] = runtimeConfig_.sunSoftCap; globPtr->globalParams1[1] = runtimeConfig_.ambientBoost;
        globPtr->globalParams1[2] = runtimeConfig_.shadowScale; globPtr->globalParams1[3] = runtimeConfig_.alphaBoost;
        globPtr->charParams[0] = static_cast<float>(charId); globPtr->charParams[1] = hasDirectionalLight ? 1.0f : 0.0f;
        globPtr->charParams[2] = (charProf && charProf->lutSrv) ? 1.0f : 0.0f;
        globPtr->charParams[3] = (charProf && charProf->matcapSrv) ? (charProf->matcapIsAtlas ? 2.0f : 1.0f) : 0.0f;
        globPtr->extraParams[0] = hasDepthTex ? 1.0f : 0.0f; globPtr->extraParams[1] = hasShadowTex ? 1.0f : 0.0f;
        const int miscBit = (miscGlobalsShift_.load(std::memory_order_acquire) != 0) ? 4 : 0;
        globPtr->extraParams[2] = static_cast<float>((hasSpecTex ? 1 : 0) + (hasStencilTex ? 2 : 0) + miscBit);
        globPtr->extraParams[3] = static_cast<float>(runtimeConfig_.debugMode);
        if (charProf) for (size_t idx = 0; idx < charProf->slots.size() && idx < kMaxVToonMaterialSlots; ++idx) globPtr->activeMaterials[idx] = charProf->slots[idx];
        d3dCtx->Unmap(targetGlobalCb, 0);
    }

    std::mutex stateMutex_;
    std::shared_mutex shaderMutex_;
    std::shared_mutex texCacheMutex_;
    VToonRuntimeConfig runtimeConfig_{};
    ID3D11Device* d3dDevice_ = nullptr;
    ID3D11DeviceContext* immContext_ = nullptr;
    std::atomic<bool> configEnabled_{true};
    std::atomic<bool> shadersCompiled_{false};
    std::atomic<bool> compilingInternalShaders_{false};
    std::atomic<bool> hasPendingProbes_{false};
    ID3D11PixelShader* psPedGbuf_ = nullptr;
    ID3D11PixelShader* psPedGbufStd_ = nullptr;
    ID3D11PixelShader* psPedGbufA2C_ = nullptr;
    ID3D11PixelShader* psOverlay_ = nullptr;
    ID3D11PixelShader* psOverlayMsaa_ = nullptr;
    ID3D11PixelShader* psForwardAlpha_ = nullptr;
    VToonWatermarkProber watermarkProber_{};
    VToonLiveDiagDumper liveDiagDumper_{};
    ID3D11Buffer* cbGlobal_ = nullptr;
    ID3D11Buffer* cbDraw_ = nullptr;
    ID3D11SamplerState* linearClampSamp_ = nullptr;
    ID3D11BlendState* opaqueBlendState_ = nullptr;
    ID3D11RasterizerState* cullNoneRastState_ = nullptr;
    ID3D11DepthStencilState* depthDisabledState_ = nullptr;
    ID3D11Texture2D* maskTex_ = nullptr;
    ID3D11RenderTargetView* maskRtv_ = nullptr;
    ID3D11ShaderResourceView* maskSrv_ = nullptr;
    UINT maskWidth_ = 0;
    UINT maskHeight_ = 0;
    UINT maskSampleCount_ = 0;
    std::atomic<UINT> swapWidth_{0u};
    std::atomic<UINT> swapHeight_{0u};
    std::atomic<bool> maskNeedsClearOnNextGbuf_{true};
    std::atomic<bool> gbufActiveThisPass_{false};
    std::atomic<uint64_t> lastOvlDrawSeq_{0u};
    std::atomic<uint32_t> frameGbufCount_{0u};
    std::atomic<uint32_t> charsSeenMask_{0u};
    std::atomic<int> miscGlobalsShift_{1};
    VToonDiagTelemetry diagState_{};
    std::vector<std::pair<D3D11_BLEND_DESC, ID3D11BlendState*>> rt4BlendCache_;
    std::unordered_map<ID3D11PixelShader*, ShaderClassification> shaderMap_;
    std::unordered_map<ID3D11Resource*, CachedTexCharEntry> texCharCache_;
    std::vector<PendingProbeItem> pendingProbes_;
};

}  // namespace gtav_vtoon
