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

#include <d3dcompiler.h>

namespace gtav_vtoon {

inline thread_local bool gVToonBypassDrawHook = false;

struct ScopedDrawHookBypass {
    bool prevValue = false;
    ScopedDrawHookBypass() : prevValue(gVToonBypassDrawHook) { gVToonBypassDrawHook = true; }
    ~ScopedDrawHookBypass() { gVToonBypassDrawHook = prevValue; }
};

/** Self-contained 2x1 GPU readback pass decoding VToon character ID watermarks. */
class VToonWatermarkProber {
public:
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

        ID3DBlob* vsBlob = nullptr;
        ID3DBlob* psBlob = nullptr;
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

        ready_ = (vsProbe_ && psProbe_ && probeRtv_ && probeStagingTex_);
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
        d3dCtx->PSSetShader(psProbe_, nullptr, 0);
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
            }
            d3dCtx->Unmap(probeStagingTex_, 0);
        }
        return outCharId;
    }

private:
    bool ready_ = false;
    ID3D11VertexShader* vsProbe_ = nullptr;
    ID3D11PixelShader* psProbe_ = nullptr;
    ID3D11Texture2D* probeRtTex_ = nullptr;
    ID3D11RenderTargetView* probeRtv_ = nullptr;
    ID3D11Texture2D* probeStagingTex_ = nullptr;
    ID3D11BlendState* opaqueBlendState_ = nullptr;
    ID3D11RasterizerState* cullNoneRastState_ = nullptr;
    ID3D11DepthStencilState* depthDisabledState_ = nullptr;
};

}  // namespace gtav_vtoon
