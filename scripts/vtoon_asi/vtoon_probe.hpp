#pragma once
/*
 * vtoon_probe.hpp
 * ===============
 * Layer 3a (GPU Watermark Prober):
 * Compiles a minimal 2x1 fullscreen probe pass that inspects mip 0 bottom-right
 * 8x4 signature blocks on resident DXT1/DXT5 character atlas SRVs, safely preserving
 * all D3D11 pipeline state so world textures are skipped in O(1) after cache warmup.
 */

#include "vtoon_config.hpp"

#include <atomic>
#include <cstdio>
#include <d3dcompiler.h>

namespace gtav_vtoon {

inline thread_local bool gVToonBypassDrawHook = false;
inline thread_local bool gInVToonDrawDispatch = false;

struct ScopedDrawHookBypass {
    bool prevValue = false;
    ScopedDrawHookBypass() : prevValue(gVToonBypassDrawHook) { gVToonBypassDrawHook = true; }
    ~ScopedDrawHookBypass() { gVToonBypassDrawHook = prevValue; }
};

struct ScopedDrawDispatchGuard {
    bool prevValue = false;
    ScopedDrawDispatchGuard() : prevValue(gInVToonDrawDispatch) { gInVToonDrawDispatch = true; }
    ~ScopedDrawDispatchGuard() { gInVToonDrawDispatch = prevValue; }
};

/** Self-contained 2x1 GPU readback pass decoding VToon character ID watermarks. */
class VToonWatermarkProber {
public:
    static bool IsSrgbFormat(DXGI_FORMAT fmt) {
        switch (fmt) {
            case DXGI_FORMAT_R8G8B8A8_UNORM_SRGB:
            case DXGI_FORMAT_BC1_UNORM_SRGB:
            case DXGI_FORMAT_BC2_UNORM_SRGB:
            case DXGI_FORMAT_BC3_UNORM_SRGB:
            case DXGI_FORMAT_B8G8R8A8_UNORM_SRGB:
            case DXGI_FORMAT_B8G8R8X8_UNORM_SRGB:
            case DXGI_FORMAT_BC7_UNORM_SRGB:
                return true;
            default:
                return false;
        }
    }

    bool Initialize(
        ID3D11Device* d3dDevice,
        ID3D11BlendState* opaqueBlendState,
        ID3D11RasterizerState* cullNoneRastState,
        ID3D11DepthStencilState* depthDisabledState
    ) {
        if (!d3dDevice) {
            return false;
        }
        opaqueBlendState_ = opaqueBlendState;
        cullNoneRastState_ = cullNoneRastState;
        depthDisabledState_ = depthDisabledState;

        const char* probeVsHlsl =
            "void MainProbeVS(uint vtxId : SV_VertexID, out float4 outPos : SV_Position) {"
            "  float2 grid = float2((vtxId == 1) ? 3.0 : -1.0, (vtxId == 2) ? 3.0 : -1.0);"
            "  outPos = float4(grid, 0.0, 1.0);"
            "}";
        const char* probePsHlsl =
            "Texture2D srcTex : register(t0);"
            "float4 MainProbePS(float4 svPos : SV_Position) : SV_Target0 {"
            "  uint widthVal = 0; uint heightVal = 0;"
            "  srcTex.GetDimensions(widthVal, heightVal);"
            "  int pxX = ((int)svPos.x == 0) ? max((int)widthVal - 6, 0) : max((int)widthVal - 2, 0);"
            "  int pxY = max((int)heightVal - 2, 0);"
            "  return srcTex.Load(int3(pxX, pxY, 0));"
            "}";
        const char* probePsSrgbHlsl =
            "Texture2D srcTex : register(t0);"
            "float LinearToSrgbChan(float linVal) {"
            "  float clamped = saturate(linVal);"
            "  return (clamped <= 0.0031308) ? (12.92 * clamped) : (1.055 * pow(max(clamped, 1e-7), 1.0 / 2.4) - 0.055);"
            "}"
            "float4 MainProbeSrgbPS(float4 svPos : SV_Position) : SV_Target0 {"
            "  uint widthVal = 0; uint heightVal = 0;"
            "  srcTex.GetDimensions(widthVal, heightVal);"
            "  int pxX = ((int)svPos.x == 0) ? max((int)widthVal - 6, 0) : max((int)widthVal - 2, 0);"
            "  int pxY = max((int)heightVal - 2, 0);"
            "  float4 linPx = srcTex.Load(int3(pxX, pxY, 0));"
            "  return float4(LinearToSrgbChan(linPx.r), LinearToSrgbChan(linPx.g), LinearToSrgbChan(linPx.b), linPx.a);"
            "}";

        ID3DBlob* vsBlob = nullptr;
        ID3DBlob* psBlob = nullptr;
        ID3DBlob* psSrgbBlob = nullptr;
        ID3DBlob* errBlob = nullptr;
        if (SUCCEEDED(D3DCompile(probeVsHlsl, std::strlen(probeVsHlsl), "probe_vs", nullptr, nullptr,
                                 "MainProbeVS", "vs_4_0", 0, 0, &vsBlob, &errBlob)) && vsBlob) {
            d3dDevice->CreateVertexShader(vsBlob->GetBufferPointer(), vsBlob->GetBufferSize(), nullptr, &vsProbe_);
            vsBlob->Release();
        }
        if (errBlob) { errBlob->Release(); errBlob = nullptr; }

        if (SUCCEEDED(D3DCompile(probePsHlsl, std::strlen(probePsHlsl), "probe_ps", nullptr, nullptr,
                                 "MainProbePS", "ps_4_0", 0, 0, &psBlob, &errBlob)) && psBlob) {
            d3dDevice->CreatePixelShader(psBlob->GetBufferPointer(), psBlob->GetBufferSize(), nullptr, &psProbe_);
            psBlob->Release();
        }
        if (errBlob) { errBlob->Release(); errBlob = nullptr; }

        if (SUCCEEDED(D3DCompile(probePsSrgbHlsl, std::strlen(probePsSrgbHlsl), "probe_ps_srgb", nullptr, nullptr,
                                 "MainProbeSrgbPS", "ps_4_0", 0, 0, &psSrgbBlob, &errBlob)) && psSrgbBlob) {
            d3dDevice->CreatePixelShader(psSrgbBlob->GetBufferPointer(), psSrgbBlob->GetBufferSize(), nullptr, &psProbeSrgb_);
            psSrgbBlob->Release();
        }
        if (errBlob) errBlob->Release();

        D3D11_TEXTURE2D_DESC probeRtDesc{};
        probeRtDesc.Width = 2;
        probeRtDesc.Height = 1;
        probeRtDesc.MipLevels = 1;
        probeRtDesc.ArraySize = 1;
        probeRtDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
        probeRtDesc.SampleDesc.Count = 1;
        probeRtDesc.Usage = D3D11_USAGE_DEFAULT;
        probeRtDesc.BindFlags = D3D11_BIND_RENDER_TARGET;
        d3dDevice->CreateTexture2D(&probeRtDesc, nullptr, &probeRtTex_);
        if (probeRtTex_) {
            d3dDevice->CreateRenderTargetView(probeRtTex_, nullptr, &probeRtv_);
        }
        probeRtDesc.Usage = D3D11_USAGE_STAGING;
        probeRtDesc.BindFlags = 0;
        probeRtDesc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
        d3dDevice->CreateTexture2D(&probeRtDesc, nullptr, &probeStagingTex_);

        ready_ = (vsProbe_ && psProbe_ && psProbeSrgb_ && probeRtv_ && probeStagingTex_);
        return ready_;
    }

    bool IsReady() const { return ready_; }

    int ProbeTexture(
        ID3D11DeviceContext* d3dCtx,
        ID3D11ShaderResourceView* diffSrv,
        ID3D11Resource* baseRes
    ) {
        if (!ready_ || !d3dCtx || !diffSrv || !baseRes) {
            return 0;
        }
        ID3D11Texture2D* tex2d = nullptr;
        if (FAILED(baseRes->QueryInterface(__uuidof(ID3D11Texture2D), reinterpret_cast<void**>(&tex2d))) || !tex2d) {
            return 0;
        }
        D3D11_TEXTURE2D_DESC desc{};
        tex2d->GetDesc(&desc);
        tex2d->Release();
        if (desc.Width < 256 || desc.Height < 256 || desc.SampleDesc.Count > 1) {
            return 0;
        }
        D3D11_SHADER_RESOURCE_VIEW_DESC srvDesc{};
        diffSrv->GetDesc(&srvDesc);
        const bool isSrgb = IsSrgbFormat(srvDesc.Format) || IsSrgbFormat(desc.Format);
        ID3D11PixelShader* activePsProbe = isSrgb ? psProbeSrgb_ : psProbe_;

        // Capture OM/RS/IA/Shader stages around the 2x1 watermark readback draw
        ID3D11RenderTargetView* savedRtvs[8] = {};
        ID3D11DepthStencilView* savedDsv = nullptr;
        d3dCtx->OMGetRenderTargets(8, savedRtvs, &savedDsv);
        D3D11_VIEWPORT savedVps[16] = {};
        UINT numVps = 16;
        d3dCtx->RSGetViewports(&numVps, savedVps);
        ID3D11InputLayout* savedLayout = nullptr;
        d3dCtx->IAGetInputLayout(&savedLayout);
        D3D11_PRIMITIVE_TOPOLOGY savedTopo = D3D11_PRIMITIVE_TOPOLOGY_UNDEFINED;
        d3dCtx->IAGetPrimitiveTopology(&savedTopo);
        ID3D11VertexShader* savedVs = nullptr;
        ID3D11ClassInstance* savedVsInst[8] = {};
        UINT savedVsInstCount = 8;
        d3dCtx->VSGetShader(&savedVs, savedVsInst, &savedVsInstCount);
        ID3D11PixelShader* savedPs = nullptr;
        ID3D11ClassInstance* savedPsInst[8] = {};
        UINT savedPsInstCount = 8;
        d3dCtx->PSGetShader(&savedPs, savedPsInst, &savedPsInstCount);
        ID3D11GeometryShader* savedGs = nullptr;
        ID3D11ClassInstance* savedGsInst[8] = {};
        UINT savedGsInstCount = 8;
        d3dCtx->GSGetShader(&savedGs, savedGsInst, &savedGsInstCount);
        ID3D11HullShader* savedHs = nullptr;
        ID3D11ClassInstance* savedHsInst[8] = {};
        UINT savedHsInstCount = 8;
        d3dCtx->HSGetShader(&savedHs, savedHsInst, &savedHsInstCount);
        ID3D11DomainShader* savedDs = nullptr;
        ID3D11ClassInstance* savedDsInst[8] = {};
        UINT savedDsInstCount = 8;
        d3dCtx->DSGetShader(&savedDs, savedDsInst, &savedDsInstCount);
        ID3D11BlendState* savedBlend = nullptr;
        float savedBlendFactor[4] = {};
        UINT savedSampleMask = 0xFFFFFFFFu;
        d3dCtx->OMGetBlendState(&savedBlend, savedBlendFactor, &savedSampleMask);
        ID3D11DepthStencilState* savedDepth = nullptr;
        UINT savedStencilRef = 0;
        d3dCtx->OMGetDepthStencilState(&savedDepth, &savedStencilRef);
        ID3D11RasterizerState* savedRast = nullptr;
        d3dCtx->RSGetState(&savedRast);
        ID3D11ShaderResourceView* savedSrv0 = nullptr;
        d3dCtx->PSGetShaderResources(0, 1, &savedSrv0);

        D3D11_VIEWPORT probeVp{};
        probeVp.Width = 2.0f;
        probeVp.Height = 1.0f;
        probeVp.MaxDepth = 1.0f;
        d3dCtx->OMSetRenderTargets(1, &probeRtv_, nullptr);
        d3dCtx->OMSetBlendState(opaqueBlendState_, nullptr, 0xFFFFFFFFu);
        d3dCtx->OMSetDepthStencilState(depthDisabledState_, 0);
        d3dCtx->RSSetState(cullNoneRastState_);
        d3dCtx->RSSetViewports(1, &probeVp);
        d3dCtx->IASetInputLayout(nullptr);
        d3dCtx->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
        d3dCtx->VSSetShader(vsProbe_, nullptr, 0);
        d3dCtx->GSSetShader(nullptr, nullptr, 0);
        d3dCtx->HSSetShader(nullptr, nullptr, 0);
        d3dCtx->DSSetShader(nullptr, nullptr, 0);
        d3dCtx->PSSetShader(activePsProbe, nullptr, 0);
        d3dCtx->PSSetShaderResources(0, 1, &diffSrv);
        {
            ScopedDrawHookBypass bypassGuard;
            d3dCtx->Draw(3, 0);
        }
        d3dCtx->CopyResource(probeStagingTex_, probeRtTex_);

        // Restore all captured GPU state immediately
        d3dCtx->PSSetShaderResources(0, 1, &savedSrv0);
        if (savedSrv0) savedSrv0->Release();
        d3dCtx->RSSetState(savedRast);
        if (savedRast) savedRast->Release();
        d3dCtx->OMSetDepthStencilState(savedDepth, savedStencilRef);
        if (savedDepth) savedDepth->Release();
        d3dCtx->OMSetBlendState(savedBlend, savedBlendFactor, savedSampleMask);
        if (savedBlend) savedBlend->Release();
        d3dCtx->DSSetShader(savedDs, savedDsInst, savedDsInstCount);
        if (savedDs) savedDs->Release();
        for (UINT idx = 0; idx < savedDsInstCount; ++idx) { if (savedDsInst[idx]) savedDsInst[idx]->Release(); }
        d3dCtx->HSSetShader(savedHs, savedHsInst, savedHsInstCount);
        if (savedHs) savedHs->Release();
        for (UINT idx = 0; idx < savedHsInstCount; ++idx) { if (savedHsInst[idx]) savedHsInst[idx]->Release(); }
        d3dCtx->GSSetShader(savedGs, savedGsInst, savedGsInstCount);
        if (savedGs) savedGs->Release();
        for (UINT idx = 0; idx < savedGsInstCount; ++idx) { if (savedGsInst[idx]) savedGsInst[idx]->Release(); }
        d3dCtx->PSSetShader(savedPs, savedPsInst, savedPsInstCount);
        if (savedPs) savedPs->Release();
        for (UINT idx = 0; idx < savedPsInstCount; ++idx) { if (savedPsInst[idx]) savedPsInst[idx]->Release(); }
        d3dCtx->VSSetShader(savedVs, savedVsInst, savedVsInstCount);
        if (savedVs) savedVs->Release();
        for (UINT idx = 0; idx < savedVsInstCount; ++idx) { if (savedVsInst[idx]) savedVsInst[idx]->Release(); }
        d3dCtx->IASetPrimitiveTopology(savedTopo);
        d3dCtx->IASetInputLayout(savedLayout);
        if (savedLayout) savedLayout->Release();
        d3dCtx->RSSetViewports(numVps, savedVps);
        d3dCtx->OMSetRenderTargets(8, savedRtvs, savedDsv);
        for (UINT idx = 0; idx < 8; ++idx) { if (savedRtvs[idx]) savedRtvs[idx]->Release(); }
        if (savedDsv) savedDsv->Release();

        int outCharId = 0;
        D3D11_MAPPED_SUBRESOURCE mapped{};
        if (SUCCEEDED(d3dCtx->Map(probeStagingTex_, 0, D3D11_MAP_READ, 0, &mapped)) && mapped.pData) {
            const uint8_t* pxData = static_cast<const uint8_t*>(mapped.pData);
            uint8_t blk0R = pxData[0];
            uint8_t blk0G = pxData[1];
            uint8_t blk0B = pxData[2];
            uint8_t blk1R = pxData[4];
            uint8_t blk1G = pxData[5];
            uint8_t blk1B = pxData[6];
            if (blk0R >= 210 && blk0G <= 45 && blk0B >= 210 && blk1G >= 210 && blk1B <= 48) {
                int decoded = static_cast<int>((blk1R + 8) / 16);
                if (decoded >= 1 && decoded < kMaxVToonCharacters) {
                    outCharId = decoded;
                    LogVToonMessage("Detected VToon texture watermark char_id=" + std::to_string(outCharId));
                }
            } else if (blk0R >= 210 && blk0G <= 45 && blk0B >= 210) {
                static std::atomic<bool> loggedBlkMismatch{false};
                if (!loggedBlkMismatch.exchange(true)) {
                    LogVToonMessage(
                        "Probe saw magenta blk0 without valid blk1 (w=" + std::to_string(desc.Width) +
                        ", fmt=" + std::to_string(static_cast<int>(srvDesc.Format)) +
                        ", blk1=" + std::to_string(blk1R) + "/" + std::to_string(blk1G) + "/" + std::to_string(blk1B) + ")"
                    );
                }
            }
            d3dCtx->Unmap(probeStagingTex_, 0);
        }
        return outCharId;
    }

private:
    bool ready_ = false;
    ID3D11VertexShader* vsProbe_ = nullptr;
    ID3D11PixelShader* psProbe_ = nullptr;
    ID3D11PixelShader* psProbeSrgb_ = nullptr;
    ID3D11Texture2D* probeRtTex_ = nullptr;
    ID3D11RenderTargetView* probeRtv_ = nullptr;
    ID3D11Texture2D* probeStagingTex_ = nullptr;
    ID3D11BlendState* opaqueBlendState_ = nullptr;
    ID3D11RasterizerState* cullNoneRastState_ = nullptr;
    ID3D11DepthStencilState* depthDisabledState_ = nullptr;
};

/** Throttled live constant-buffer & render-target snapshot logger for runtime diagnostics. */
class VToonLiveDiagDumper {
public:
    bool Initialize(ID3D11Device* d3dDevice) {
        if (!d3dDevice || cbStageBuf_) return (cbStageBuf_ != nullptr);
        D3D11_BUFFER_DESC stageDesc{1024u, D3D11_USAGE_STAGING, 0u, D3D11_CPU_ACCESS_READ, 0u, 0u};
        return SUCCEEDED(d3dDevice->CreateBuffer(&stageDesc, nullptr, &cbStageBuf_)) && (cbStageBuf_ != nullptr);
    }

    static std::string FmtVec4(const float* ptr) {
        char buf[96] = {};
        std::snprintf(buf, sizeof(buf), "(%.3f,%.3f,%.3f,%.3f)", ptr[0], ptr[1], ptr[2], ptr[3]);
        return std::string(buf);
    }

    bool ReadCbFloats(ID3D11DeviceContext* d3dCtx, UINT psSlot, float* outFloats, UINT maxFloats) {
        std::memset(outFloats, 0, sizeof(float) * maxFloats);
        if (!d3dCtx || !cbStageBuf_ || d3dCtx->GetType() != D3D11_DEVICE_CONTEXT_IMMEDIATE) return false;
        ID3D11Buffer* srcCb = nullptr;
        d3dCtx->PSGetConstantBuffers(psSlot, 1, &srcCb);
        if (!srcCb) return false;
        D3D11_BUFFER_DESC cbDesc{};
        srcCb->GetDesc(&cbDesc);
        UINT copyBytes = (cbDesc.ByteWidth < maxFloats * 4u) ? cbDesc.ByteWidth : (maxFloats * 4u);
        copyBytes &= ~15u;
        bool okRead = false;
        if (copyBytes >= 16u) {
            D3D11_BOX srcBox{0u, 0u, 0u, copyBytes, 1u, 1u};
            d3dCtx->CopySubresourceRegion(cbStageBuf_, 0u, 0u, 0u, 0u, srcCb, 0u, &srcBox);
            D3D11_MAPPED_SUBRESOURCE mapped{};
            if (SUCCEEDED(d3dCtx->Map(cbStageBuf_, 0u, D3D11_MAP_READ, 0u, &mapped)) && mapped.pData) {
                std::memcpy(outFloats, mapped.pData, copyBytes);
                d3dCtx->Unmap(cbStageBuf_, 0u);
                okRead = true;
            }
        }
        srcCb->Release();
        return okRead;
    }

    void LogPedGbufLive(ID3D11DeviceContext* d3dCtx, int charId, int miscShift, UINT numRtvs) {
        float cbTwo[64] = {}, cbFive[20] = {}, cbThirteen[24] = {};
        bool okTwo = ReadCbFloats(d3dCtx, 2u, cbTwo, 64u);
        bool okFive = ReadCbFloats(d3dCtx, 5u, cbFive, 20u);
        bool okThirteen = ReadCbFloats(d3dCtx, 13u, cbThirteen, 24u);
        LogVToonMessage("LiveSnap PedGbuf char=" + std::to_string(charId) + " shift=" + std::to_string(miscShift) +
            " rtvs=" + std::to_string(numRtvs) +
            " cb2[11]=" + (okTwo ? FmtVec4(&cbTwo[44]) : "none") +
            " cb2[12]=" + (okTwo ? FmtVec4(&cbTwo[48]) : "none") +
            " cb2[13]=" + (okTwo ? FmtVec4(&cbTwo[52]) : "none") +
            " cb2[14]=" + (okTwo ? FmtVec4(&cbTwo[56]) : "none") +
            " cb5[3]=" + (okFive ? FmtVec4(&cbFive[12]) : "none") +
            " cb13[4]=" + (okThirteen ? FmtVec4(&cbThirteen[16]) : "none"));
    }

    void LogOverlayLive(ID3D11DeviceContext* d3dCtx, int kindVal, int miscShift, bool depthOk, bool shdOk, bool specOk, bool stnOk) {
        float cbTwo[64] = {}, cbThree[208] = {}, cbEleven[20] = {};
        bool okTwo = ReadCbFloats(d3dCtx, 2u, cbTwo, 64u);
        bool okThree = ReadCbFloats(d3dCtx, 3u, cbThree, 208u);
        bool okEleven = ReadCbFloats(d3dCtx, 11u, cbEleven, 20u);
        std::string rtvInfo = "none";
        ID3D11RenderTargetView* curRtv = nullptr;
        d3dCtx->OMGetRenderTargets(1u, &curRtv, nullptr);
        if (curRtv) {
            ID3D11Resource* rtRes = nullptr;
            curRtv->GetResource(&rtRes);
            curRtv->Release();
            if (rtRes) {
                ID3D11Texture2D* tex2d = nullptr;
                if (SUCCEEDED(rtRes->QueryInterface(__uuidof(ID3D11Texture2D), reinterpret_cast<void**>(&tex2d))) && tex2d) {
                    D3D11_TEXTURE2D_DESC rdesc{};
                    tex2d->GetDesc(&rdesc);
                    tex2d->Release();
                    rtvInfo = std::to_string(rdesc.Width) + "x" + std::to_string(rdesc.Height) +
                        " ms=" + std::to_string(rdesc.SampleDesc.Count) + " fmt=" + std::to_string(static_cast<int>(rdesc.Format));
                }
                rtRes->Release();
            }
        }
        LogVToonMessage("LiveSnap Overlay kind=" + std::to_string(kindVal) + " shift=" + std::to_string(miscShift) +
            " rt=" + rtvInfo + " flags=(" + std::to_string(depthOk ? 1 : 0) + std::to_string(shdOk ? 1 : 0) +
            std::to_string(specOk ? 1 : 0) + std::to_string(stnOk ? 1 : 0) + ")" +
            " cb2[12..14]=" + (okTwo ? (FmtVec4(&cbTwo[48]) + " " + FmtVec4(&cbTwo[52]) + " " + FmtVec4(&cbTwo[56])) : "none") +
            " cb3[45]=" + (okThree ? FmtVec4(&cbThree[180]) : "none") +
            " cb3[47]=" + (okThree ? FmtVec4(&cbThree[188]) : "none") +
            " cb3[49]=" + (okThree ? FmtVec4(&cbThree[196]) : "none") +
            " cb11[1]=" + (okEleven ? FmtVec4(&cbEleven[4]) : "none") +
            " cb11[3]=" + (okEleven ? FmtVec4(&cbEleven[12]) : "none"));
    }

    void LogForwardAlphaLive(ID3D11DeviceContext* d3dCtx, int charId, int miscShift, bool hasCsm) {
        float cbTwo[64] = {}, cbThree[208] = {}, cbFive[20] = {}, cbThirteen[24] = {};
        bool okTwo = ReadCbFloats(d3dCtx, 2u, cbTwo, 64u);
        bool okThree = ReadCbFloats(d3dCtx, 3u, cbThree, 208u);
        bool okFive = ReadCbFloats(d3dCtx, 5u, cbFive, 20u);
        bool okThirteen = ReadCbFloats(d3dCtx, 13u, cbThirteen, 24u);
        int numFwdLights = 0;
        if (okThree) std::memcpy(&numFwdLights, &cbThree[8], sizeof(int));
        LogVToonMessage("LiveSnap FwdAlpha char=" + std::to_string(charId) + " shift=" + std::to_string(miscShift) +
            " csm=" + std::to_string(hasCsm ? 1 : 0) +
            " nL=" + std::to_string(numFwdLights) +
            " cb2[12..14]=" + (okTwo ? (FmtVec4(&cbTwo[48]) + " " + FmtVec4(&cbTwo[52]) + " " + FmtVec4(&cbTwo[56])) : "none") +
            " cb3[0..1]=" + (okThree ? (FmtVec4(&cbThree[0]) + " " + FmtVec4(&cbThree[4])) : "none") +
            " cb3[3/19]=" + (okThree ? (FmtVec4(&cbThree[12]) + " " + FmtVec4(&cbThree[76])) : "none") +
            " cb3[45/46]=" + (okThree ? (FmtVec4(&cbThree[180]) + " " + FmtVec4(&cbThree[184])) : "none") +
            " cb5[3]=" + (okFive ? FmtVec4(&cbFive[12]) : "none") +
            " cb13[4]=" + (okThirteen ? FmtVec4(&cbThirteen[16]) : "none"));
    }

private:
    ID3D11Buffer* cbStageBuf_ = nullptr;
};

struct PendingProbeItem {
    ID3D11ShaderResourceView* srvPtr = nullptr;
    ID3D11Resource* resPtr = nullptr;
    uint64_t sigHash = 0;
};

struct CachedTexCharEntry {
    uint64_t sigHash = 0;
    int charId = 0;
};

inline uint64_t ComputeTextureResourceSignature(ID3D11Resource* baseRes) {
    if (!baseRes) return 0u;
    ID3D11Texture2D* texObj = nullptr;
    if (FAILED(baseRes->QueryInterface(__uuidof(ID3D11Texture2D), reinterpret_cast<void**>(&texObj))) || !texObj) return 0u;
    D3D11_TEXTURE2D_DESC texDesc{};
    texObj->GetDesc(&texDesc);
    texObj->Release();
    uint64_t sigVal = static_cast<uint64_t>(texDesc.Width & 0xFFFFu);
    sigVal |= (static_cast<uint64_t>(texDesc.Height & 0xFFFFu) << 16);
    sigVal |= (static_cast<uint64_t>(static_cast<uint32_t>(texDesc.Format) & 0xFFu) << 32);
    sigVal |= (static_cast<uint64_t>(texDesc.MipLevels & 0xFFu) << 40);
    sigVal |= (static_cast<uint64_t>(texDesc.ArraySize & 0xFFu) << 48);
    return sigVal;
}

/** Per-frame and periodic diagnostic telemetry counters for VToon hooks. */
struct VToonDiagTelemetry {
    std::atomic<uint32_t> loggedMilestones{0u};
    std::atomic<uint32_t> activeFrames{0u};
    std::atomic<uint32_t> gbufCalls{0u};
    std::atomic<uint32_t> minGbuf{9999u};
    std::atomic<uint32_t> maxGbuf{0u};
    std::atomic<uint32_t> defGbufCalls{0u};
    std::atomic<uint32_t> skippedGbuf{0u};
    std::atomic<uint32_t> skipRtv{0u};
    std::atomic<uint32_t> indBlend{0u};
    std::atomic<uint32_t> fwdAlphaCalls{0u};
    std::atomic<uint32_t> overlayCalls{0u};
    std::atomic<uint32_t> ovlSunCalls{0u};
    std::atomic<uint32_t> ovlAmbCalls{0u};
    std::atomic<uint32_t> maxOvlGap{0u};
    std::atomic<uint32_t> additiveSkip{0u};
    std::atomic<uint32_t> rehooks{0u};
    std::atomic<uint32_t> rehookMask{0u};
    std::atomic<uint32_t> postFlushCatches{0u};
    std::atomic<uint32_t> periodFrames{0u};
    std::atomic<bool> forceLiveDump{true};
    std::atomic<bool> wantDumpGbuf{true};
    std::atomic<bool> wantDumpOvl{true};
    std::atomic<bool> wantDumpFwd{true};
    std::atomic<uint32_t> gbufTid{0u};
    std::atomic<uint32_t> ovlTid{0u};
    std::atomic<uint32_t> presTid{0u};

    void LogMilestoneOnce(uint32_t flagBit, const std::string& msgText) {
        if ((loggedMilestones.fetch_or(flagBit, std::memory_order_relaxed) & flagBit) == 0u) LogVToonMessage(msgText);
    }

    void RecordVTableRehook(uint32_t patchedMask) {
        if (patchedMask == 0u) return;
        rehooks.fetch_add(1u, std::memory_order_relaxed);
        rehookMask.fetch_or(patchedMask, std::memory_order_relaxed);
    }

    void RecordPostFlushCatch() { postFlushCatches.fetch_add(1u, std::memory_order_relaxed); }

    void RecordFrameGbufStats(uint32_t prevCnt) {
        if (prevCnt == 0u) return;
        uint32_t curMin = minGbuf.load(std::memory_order_relaxed);
        while (prevCnt < curMin && !minGbuf.compare_exchange_weak(curMin, prevCnt, std::memory_order_relaxed)) {}
        uint32_t curMax = maxGbuf.load(std::memory_order_relaxed);
        while (prevCnt > curMax && !maxGbuf.compare_exchange_weak(curMax, prevCnt, std::memory_order_relaxed)) {}
    }

    void RecordOvlGap(uint32_t gapVal) {
        uint32_t curMaxGap = maxOvlGap.load(std::memory_order_relaxed);
        while (gapVal > curMaxGap && !maxOvlGap.compare_exchange_weak(curMaxGap, gapVal, std::memory_order_relaxed)) {}
    }

    bool NeedsEndFrameDiag() const {
        return activeFrames.load(std::memory_order_relaxed) < 60u && gbufCalls.load(std::memory_order_relaxed) > 0u;
    }

    void OnEndFramePresent(int miscShift, UINT swapWidth, UINT swapHeight) {
        presTid.store(GetCurrentThreadId(), std::memory_order_relaxed);
        const uint32_t gbufTotal = gbufCalls.load(std::memory_order_relaxed);
        if (gbufTotal == 0u) return;
        const uint32_t activeIdx = activeFrames.fetch_add(1u, std::memory_order_relaxed) + 1u;
        const uint32_t perIdx = periodFrames.fetch_add(1u, std::memory_order_relaxed) + 1u;
        if (forceLiveDump.exchange(false, std::memory_order_acq_rel) || activeIdx == 2u || perIdx == 180u) {
            wantDumpGbuf.store(true, std::memory_order_release);
            wantDumpOvl.store(true, std::memory_order_release);
            wantDumpFwd.store(true, std::memory_order_release);
        }
        if (activeIdx == 60u || perIdx >= 180u) {
            if (perIdx >= 180u) periodFrames.store(0u, std::memory_order_relaxed);
            const uint32_t minVal = minGbuf.exchange(9999u, std::memory_order_relaxed);
            const uint32_t maxVal = maxGbuf.exchange(0u, std::memory_order_relaxed);
            const uint32_t rmask = rehookMask.exchange(0u, std::memory_order_relaxed);
            char hexBuf[16] = {};
            std::snprintf(hexBuf, sizeof(hexBuf), "0x%X", rmask);
            LogVToonMessage((activeIdx == 60u ? std::string("VToon60 diag: f=") : std::string("VToonPer diag: f=")) + std::to_string(activeIdx) +
                " gbuf=" + std::to_string(gbufTotal) + " minG=" + std::to_string(minVal < 9999u ? minVal : 0u) +
                " maxG=" + std::to_string(maxVal) + " def=" + std::to_string(defGbufCalls.load(std::memory_order_relaxed)) +
                " skipSize=" + std::to_string(skippedGbuf.load(std::memory_order_relaxed)) +
                " skipRtv=" + std::to_string(skipRtv.load(std::memory_order_relaxed)) +
                " indBlend=" + std::to_string(indBlend.load(std::memory_order_relaxed)) +
                " fwd=" + std::to_string(fwdAlphaCalls.load(std::memory_order_relaxed)) +
                " ovl=" + std::to_string(overlayCalls.load(std::memory_order_relaxed)) +
                " sun=" + std::to_string(ovlSunCalls.load(std::memory_order_relaxed)) +
                " amb=" + std::to_string(ovlAmbCalls.load(std::memory_order_relaxed)) +
                " ovlGap=" + std::to_string(maxOvlGap.load(std::memory_order_relaxed)) +
                " skipAdd=" + std::to_string(additiveSkip.load(std::memory_order_relaxed)) +
                " rehooks=" + std::to_string(rehooks.load(std::memory_order_relaxed)) + " rmask=" + hexBuf +
                " pfCatch=" + std::to_string(postFlushCatches.load(std::memory_order_relaxed)) +
                " shift=" + std::to_string(miscShift) +
                " tids=" + std::to_string(gbufTid.load(std::memory_order_relaxed)) + "/" +
                std::to_string(ovlTid.load(std::memory_order_relaxed)) + "/" + std::to_string(presTid.load(std::memory_order_relaxed)) +
                " swap=" + std::to_string(swapWidth) + "x" + std::to_string(swapHeight));
        }
    }
};

}  // namespace gtav_vtoon
