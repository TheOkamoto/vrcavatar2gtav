#pragma once
/*
 * vtoon_shaders_hlsl.hpp
 * ======================
 * Layer 2 (VToon HLSL Shaders): Embedded HLSL pixel shader sources modeled after
 * open-source lilToon (`lil_common_frag.hlsl`):
 *   - `kVToonPedGBufferHlsl` (standard + MSAA SV_Coverage A2C cutout variants):
 *     Writes calibrated GTA V GBuffer channels (`o0..o3` with `o3.w = 1.0` to bypass
 *     vanilla blurry skin SSS pass) plus `SV_Target4` VToon pixel/UV/depth tag.
 *   - `kVToonDeferredOverlayHlsl` (non-MSAA and MSAA per-sample variants):
 *     Replaces GTA V hard-Lambert PBR lighting on VToon pixels with lilToon
 *     Half-Lambert dual-border cel shading, warm SSS terminator tint, MatCap/hair
 *     highlight, Rim light, CSM cast shadows, and anti-blowout HDR calibration.
 *   - `kVToonForwardAlphaHlsl`:
 *     Replaces `ped_alpha.sps` forward pass for semi-transparent bangs and glass
 *     so eyelashes/eyebrows remain smoothly visible through wispy hair strands.
 */

namespace gtav_vtoon {

inline const char* kVToonPedGBufferHlsl = R"HLSL(
cbuffer misc_globals : register(b2) {
    float4 miscPadBefore[11];
    float4 globalScalars;
    float4 globalScalars2;
    float4 globalScalars3;
    float4 globalScreenSize;
    uint4 targetAaParams;
};

cbuffer lighting_globals : register(b3) {
    float4 lightPadBefore[45];
    float4 lightIntAmb0;
    float4 lightIntAmb1;
    float4 lightExtAmb0;
    float4 lightExtAmb1;
    float4 dirAmbientColour;
};

cbuffer ped_common_shared_locals : register(b13) {
    float4 pedPadBefore[4];
    float4 matColorScale[2];
};

cbuffer VToonDrawCB : register(b9) {
    float4 drawCharInfo;
    float4 drawTint;
    float4 drawSlotPad[10];
};

Texture2D diffuseTex : register(t0);
SamplerState diffuseSamp : register(s0);

struct PedGbufInput {
    float4 svPosition  : SV_Position;
    float2 texCoord0   : TEXCOORD0;
    float3 worldNormal : TEXCOORD1;
    float4 vertColor0  : TEXCOORD3;
    bool isFrontFace   : SV_IsFrontFace;
};

struct PedGbufOutput {
    float4 targetAlbedo : SV_Target0;
    float4 targetNormal : SV_Target1;
    float4 targetSpec   : SV_Target2;
    float4 targetAoEm   : SV_Target3;
    float4 targetMask   : SV_Target4;
#ifdef VTOON_A2C_MASK
    uint outCoverage    : SV_Coverage;
#endif
};

float3 EncodeGtaWorldNormal(float3 worldNorm, out float outExtraFrac) {
    float3 unitNorm = normalize(worldNorm);
    float3 packedVec = saturate(unitNorm * 0.5 + 0.5);
    float3 scaledVec = packedVec * 255.999;
    float3 baseByte = min(floor(scaledVec), float3(255.0, 255.0, 255.0));
    float3 fracBits = clamp(floor((scaledVec - baseByte) * float3(8.0, 8.0, 4.0)),
                            float3(0.0, 0.0, 0.0), float3(7.0, 7.0, 3.0));
    outExtraFrac = dot(fracBits, float3(32.0, 4.0, 1.0)) * (1.0 / 255.0);
    return baseByte * (1.0 / 255.0);
}

bool ComputeDitherFadeKeep(float2 pixelPos, float globalAlpha) {
    if (globalAlpha >= 0.995) {
        return true;
    }
    uint pxX = (uint)pixelPos.x & 3u;
    uint pxY = (uint)pixelPos.y & 3u;
    static const float bayerMatrix[16] = {
        0.0625, 0.5625, 0.1875, 0.6875,
        0.8125, 0.3125, 0.9375, 0.4375,
        0.2500, 0.7500, 0.1250, 0.6250,
        1.0000, 0.5000, 0.8750, 0.3750
    };
    float thresholdVal = bayerMatrix[pxY * 4u + pxX];
    return globalAlpha > thresholdVal;
}

PedGbufOutput MainPedGBuffer(PedGbufInput inputData) {
    float4 texSample = diffuseTex.Sample(diffuseSamp, inputData.texCoord0);
    float fadeAlpha = inputData.vertColor0.a * globalScalars.x;
    if (!ComputeDitherFadeKeep(inputData.svPosition.xy, fadeAlpha)) {
        discard;
    }

    float effectiveAlpha = texSample.a * fadeAlpha;
    if (drawTint.w > 0.5 && effectiveAlpha < drawCharInfo.y) {
        discard;
    }

    float3 surfNormal = normalize(inputData.worldNormal);
    if (!inputData.isFrontFace) {
        surfNormal = -surfNormal;
    }

    float extraNormalBits = 0.0;
    float3 encodedNormal = EncodeGtaWorldNormal(surfNormal, extraNormalBits);

    float ambientZ = saturate(surfNormal.z * 0.5 + 0.5);
    float combinedAo = sqrt(saturate((ambientZ * 0.7 + 0.3) * 0.5));

    PedGbufOutput outputData;
    outputData.targetAlbedo = float4(saturate(texSample.rgb * matColorScale[0].x), saturate(effectiveAlpha));
    outputData.targetNormal = float4(encodedNormal, extraNormalBits);
    outputData.targetSpec   = float4(0.866, 0.14, 0.04, 1.0);
    // Setting targetAoEm.w = 1.0 ensures GTA V skips PS_pedSkinPassNG SSS blur
    outputData.targetAoEm   = float4(combinedAo, combinedAo, 0.0, 1.0);
    outputData.targetMask   = float4(drawCharInfo.x, inputData.svPosition.z, inputData.texCoord0.x, inputData.texCoord0.y);

#ifdef VTOON_A2C_MASK
    float coverageFrac = saturate((texSample.a - drawCharInfo.y) * 2.5 + 0.5);
    uint covBits = 0xFFFFFFFFu;
    if (coverageFrac < 0.99) {
        int activeCount = clamp((int)round(coverageFrac * 8.0), 1, 8);
        covBits = (activeCount >= 8) ? 0xFFFFFFFFu : ((1u << activeCount) - 1u);
    }
    outputData.outCoverage = covBits;
#endif
    return outputData;
}
)HLSL";

inline const char* kVToonCoreEvalHlsl = R"HLSL(
struct VToonMaterialData {
    float4 colorTint;
    float4 shadowColor;
    float4 shadow2ndColor;
    float4 shadowBorderColor;
    float4 rimColor;
    float4 matcapColor;
    float4 tuningA;
    float4 tuningB;
    float4 tuningC;
    float4 flagsMisc;
};

float ComputeTooningStep(float lightVal, float borderVal, float blurVal) {
    float halfBlur = max(blurVal * 0.5, 0.002);
    return smoothstep(borderVal - halfBlur, borderVal + halfBlur, lightVal);
}

float3 EvaluateLilToonSurface(
    float3 albedoLinear,
    float3 worldNorm,
    float3 viewVec,
    float3 sunDir,
    float3 sunColor,
    float3 ambientColor,
    float csmShadow,
    float naturalAo,
    float daylightScale,
    float minWorldLum,
    float maxWorldLum,
    float sunSoftCap,
    float ambientBoost,
    float shadowScale,
    float4 lutMaskSample,
    VToonMaterialData matSlot,
    Texture2D matcapTex,
    SamplerState linearSamp,
    float hasMatcapTex,
    float3 camRightVec,
    float3 camUpVec
) {
    float3 tintedAlbedo = albedoLinear * matSlot.colorTint.rgb;

    // Normalize GTA V HDR light range to lilToon calibrated exposure window
    float3 boostAmbient = ambientColor * ambientBoost;
    float3 softSun = sunColor / (1.0 + sunColor * (1.0 / max(sunSoftCap, 0.25)));
    float3 totalIncident = boostAmbient + softSun * 0.55;
    float rawLum = max(dot(totalIncident, float3(0.2126, 0.7152, 0.0722)), 1e-4);
    float clampedLum = clamp(rawLum * daylightScale, minWorldLum, maxWorldLum);
    float3 lightColor = (totalIncident / rawLum) * clampedLum;

    // lilToon _LightMinLimit and _LightMaxLimit clamp
    float3 minLight = max(lightColor * matSlot.tuningB.x, clampedLum * matSlot.tuningB.x);
    float3 maxLight = min(lightColor, clampedLum * matSlot.tuningB.y);
    lightColor = clamp(lightColor, minLight, maxLight);

    // Half-Lambert cel shading with optional soft CSM shadow cast attenuation
    float dotNL = dot(worldNorm, sunDir);
    float halfLambert = saturate(dotNL * 0.5 + 0.5);
    float csmWeight = lerp(1.0, csmShadow, saturate(matSlot.tuningA.w * shadowScale));
    float shadeInput = halfLambert * csmWeight * lerp(0.85, 1.0, naturalAo);

    float step1 = ComputeTooningStep(shadeInput, matSlot.shadowColor.w, matSlot.shadow2ndColor.w);
    float step2 = ComputeTooningStep(shadeInput, matSlot.tuningA.y, matSlot.tuningA.z);

    // Subtle colored SSS terminator border right along the 1st cel transition
    float borderSpan = max(matSlot.shadowBorderColor.w, 0.045);
    float borderFactor = saturate(1.0 - abs(shadeInput - matSlot.shadowColor.w) / borderSpan);

    float shadowMaskWeight = saturate(matSlot.tuningA.x * lutMaskSample.g);
    float3 colSh1 = tintedAlbedo * lerp(float3(1.0, 1.0, 1.0), matSlot.shadowColor.rgb, shadowMaskWeight);
    colSh1 = lerp(colSh1, colSh1 * matSlot.shadowBorderColor.rgb, borderFactor * 0.65);
    float3 colSh2 = tintedAlbedo * lerp(float3(1.0, 1.0, 1.0), matSlot.shadow2ndColor.rgb, shadowMaskWeight * 0.85);
    // Match lilToon `indirectCol = min(indirectCol, directCol)` so deep shadow2 never lightens into cyan patches
    colSh2 = min(colSh2, colSh1);

    float3 shadowedAlbedo = lerp(colSh2, colSh1, step2);
    float3 baseCelAlbedo = lerp(shadowedAlbedo, tintedAlbedo, step1);

    float3 outColor = baseCelAlbedo * lightColor;
    bool isSkinOrFace = (matSlot.flagsMisc.x > 0.5 && matSlot.flagsMisc.x < 2.5);
    bool isHairSlot = (matSlot.flagsMisc.x > 3.5 && matSlot.flagsMisc.x < 5.5);

    // View-space Rim Light (subtle on skin/face and shadow-masked on hair like lilToon _RimShadowMask)
    float dotNV = saturate(dot(worldNorm, viewVec));
    if (matSlot.tuningC.y > 0.5) {
        float rimRaw = pow(saturate(1.0 - dotNV), max(matSlot.tuningB.w, 0.25));
        float rimStep = ComputeTooningStep(rimRaw, matSlot.rimColor.w, matSlot.tuningB.z);
        float3 rimTint = lerp(matSlot.rimColor.rgb, matSlot.rimColor.rgb * tintedAlbedo, matSlot.tuningC.x);
        float rimScale = isSkinOrFace ? 0.08 : (isHairSlot ? 0.26 * lerp(0.18, 1.0, step1) : 0.35);
        float rimMask = saturate(lutMaskSample.b + (isSkinOrFace ? 0.05 : 0.35));
        outColor += rimTint * rimStep * lightColor * (rimMask * rimScale);
    }

    // View-space MatCap / Hair Angel-Ring / Metallic Earring Specular
    if (matSlot.tuningC.z > 0.5) {
        float2 matcapUv = float2(dot(worldNorm, camRightVec), dot(worldNorm, camUpVec)) * 0.5 + 0.5;
        float3 mcSample = float3(1.0, 1.0, 1.0);
        if (hasMatcapTex > 0.5) {
            mcSample = pow(max(matcapTex.SampleLevel(linearSamp, matcapUv, 0).rgb, 0.0), 2.2);
        } else {
            float fakeSpec = pow(saturate(dot(worldNorm, normalize(viewVec + float3(0.0, 0.0, 0.45)))), 14.0);
            mcSample = float3(fakeSpec, fakeSpec, fakeSpec);
        }
        float mcMask = lutMaskSample.b * matSlot.matcapColor.w;
        float mcGain = (matSlot.flagsMisc.x > 6.5) ? 0.48 : 0.30;
        outColor += mcSample * matSlot.matcapColor.rgb * lightColor * (mcMask * mcGain);
    }

    // Soft highlight shoulder compression on skin/face so bright GTA V sunlight preserves warm peach tones
    if (isSkinOrFace) {
        float skinCap = max(0.62, clampedLum * matSlot.tuningB.y);
        float3 skinExcess = max(outColor - skinCap * 0.72, 0.0);
        outColor = min(outColor, skinCap * 0.72) + skinExcess / (1.0 + skinExcess * 1.45);
    }

    // Self-illumination / eye highlight & crescent glow protection from LUT alpha mask
    if (lutMaskSample.a > 0.02) {
        float eyeLum = max(clampedLum * 0.95, 0.30);
        outColor = max(outColor, tintedAlbedo * eyeLum * saturate(lutMaskSample.a * 1.38));
    }

    return max(outColor, float3(0.0, 0.0, 0.0));
}
)HLSL";

inline const char* kVToonDeferredOverlayHlsl = R"HLSL(
cbuffer rage_matrices : register(b1) {
    float4x4 worldMtx;
    float4x4 worldViewMtx;
    float4x4 worldViewProjMtx;
    float4x4 viewInverseMtx;
};

cbuffer misc_globals : register(b2) {
    float4 miscPadBefore[11];
    float4 globalScalars;
    float4 globalScalars2;
    float4 globalScalars3;
    float4 globalScreenSize;
};

cbuffer lighting_globals : register(b3) {
    float4 gDirectionalLight;
    float4 gDirectionalColour;
    float4 lightPadMid[41];
    float4 gLightNaturalAmbient0;
    float4 gLightNaturalAmbient1;
    float4 gLightArtificialInt0;
    float4 gLightArtificialInt1;
    float4 gLightArtificialExt0;
    float4 gLightArtificialExt1;
    float4 gDirectionalAmbientColour;
};

cbuffer lighting_locals : register(b11) {
    float4 deferredLightParams[14];
};

cbuffer VToonGlobalCB : register(b7) {
    float4 globalParams0;
    float4 globalParams1;
    float4 charParams;
    float4 extraParams;
    VToonMaterialData activeMaterials[16];
};

Texture2D gDeferredShadowTex  : register(t4);
SamplerState gShadowSamp      : register(s4);

#ifdef VTOON_MSAA
Texture2DMS<float4> gBufAlbedoTex    : register(t7);
Texture2DMS<float4> gBufNormalTex    : register(t8);
Texture2DMS<float4> gBufAoEmTex      : register(t10);
Texture2DMS<uint2>  gBufStencilTex   : register(t11);
Texture2DMS<float>  gBufDepthTex     : register(t12);
Texture2DMS<float4> vtoonMaskTex     : register(t16);
#else
Texture2D gBufAlbedoTex       : register(t7);
Texture2D gBufNormalTex       : register(t8);
Texture2D gBufAoEmTex         : register(t10);
Texture2D<uint2> gBufStencilTex : register(t11);
Texture2D gBufDepthTex        : register(t12);
Texture2D vtoonMaskTex        : register(t16);
#endif

Texture2D vtoonLutTex         : register(t17);
Texture2D vtoonMatcapTex      : register(t18);
SamplerState vtoonLinearSamp  : register(s13);

struct DirOverlayInput {
    float4 svPosition : SV_Position;
    float4 texCoord0  : TEXCOORD0;
    float4 texCoord1  : TEXCOORD1;
#ifdef VTOON_MSAA
    uint sampleIndex  : SV_SampleIndex;
#endif
};

float4 MainDeferredOverlay(DirOverlayInput inputData) : SV_Target0 {
    if (globalParams0.x < 0.5) {
        discard;
    }

    int2 pxCoord = int2(inputData.svPosition.xy);
#ifdef VTOON_MSAA
    float4 maskSample = vtoonMaskTex.Load(pxCoord, inputData.sampleIndex);
    float sceneDepth = gBufDepthTex.Load(pxCoord, inputData.sampleIndex).x;
#else
    float4 maskSample = vtoonMaskTex.Load(int3(pxCoord, 0));
    float sceneDepth = gBufDepthTex.Load(int3(pxCoord, 0)).x;
#endif

    // Reject untouched world pixels or pixels occluded later in the GBuffer pass
    if (maskSample.x < 0.5 || abs(maskSample.x - charParams.x) > 0.25 ||
        (sceneDepth > 0.00001 && abs(sceneDepth - maskSample.y) > 0.00025)) {
        discard;
    }

#ifdef VTOON_MSAA
    float4 encAlbedo = gBufAlbedoTex.Load(pxCoord, inputData.sampleIndex);
    float4 encNormal = gBufNormalTex.Load(pxCoord, inputData.sampleIndex);
    float4 encAoEm   = gBufAoEmTex.Load(pxCoord, inputData.sampleIndex);
    uint stencilVal  = gBufStencilTex.Load(pxCoord, inputData.sampleIndex).y;
#else
    float4 encAlbedo = gBufAlbedoTex.Load(int3(pxCoord, 0));
    float4 encNormal = gBufNormalTex.Load(int3(pxCoord, 0));
    float4 encAoEm   = gBufAoEmTex.Load(int3(pxCoord, 0));
    uint stencilVal  = gBufStencilTex.Load(int3(pxCoord, 0)).y;
#endif

    float rawByteW = round(encNormal.w * 255.0);
    float fracX = floor(rawByteW / 32.0);
    float remVal = rawByteW - fracX * 32.0;
    float fracY = floor(remVal / 4.0);
    float fracZ = remVal - fracY * 4.0;
    float3 subFrac = float3(fracX * 0.125, fracY * 0.125, fracZ * 0.25);
    float3 baseDecoded = round(encNormal.xyz * 255.0);
    float3 worldNormal = normalize(((baseDecoded + subFrac) / 255.999) * 2.0 - 1.0);

    float2 screenUv = inputData.texCoord0.xy / inputData.texCoord0.w;
    float3 rayDir = normalize(inputData.texCoord1.xyz / inputData.texCoord1.w);
    float3 viewVec = -rayDir;

    float4 lutMask = float4(0.0, 1.0, 0.5, 0.0);
    if (charParams.z > 0.5) {
        lutMask = vtoonLutTex.SampleLevel(vtoonLinearSamp, maskSample.zw, 0);
    }
    int slotIdx = clamp((int)round(lutMask.r * 15.0), 0, 15);
    VToonMaterialData matSlot = activeMaterials[slotIdx];

    // Exact GTA V natural + interior/exterior ambient calculation from directional.asm
    float ambFactor = max(0.0, worldNormal.z + gLightNaturalAmbient0.w) * gLightNaturalAmbient1.w;
    float3 intAmb = gLightArtificialInt0.xyz * ambFactor + gLightArtificialInt1.xyz;
    float3 extAmb = gLightArtificialExt0.xyz * ambFactor + gLightArtificialExt1.xyz;
    float3 natBase = gLightNaturalAmbient0.xyz * ambFactor + gLightNaturalAmbient1.xyz;
    bool isInterior = (stencilVal & 8u) != 0u;
    float3 dirAxis = float3(gLightArtificialInt1.w, gLightArtificialExt0.w, gLightArtificialExt1.w);
    float3 skyAmb = gDirectionalAmbientColour.xyz * saturate(dot(dirAxis, worldNormal)) + natBase;
    float naturalAo = saturate(encAoEm.x);
    float artAo = saturate(encAoEm.y);
    float3 combinedAmbient = (isInterior ? intAmb * artAo : (extAmb * artAo + skyAmb * naturalAo));

    float3 sunDir = normalize(float3(0.35, -0.45, 0.82));
    float3 sunCol = float3(0.0, 0.0, 0.0);
    if (charParams.y > 0.5) {
        sunDir = normalize(-deferredLightParams[1].xyz);
        sunCol = max(deferredLightParams[3].xyz, float3(0.0, 0.0, 0.0));
    }
    float csmShadow = gDeferredShadowTex.SampleLevel(gShadowSamp, screenUv, 0).x;

    float3 camRight = normalize(cross(float3(0.0, 0.0, 1.0), rayDir + float3(1e-5, 0.0, 0.0)));
    float3 camUp = normalize(cross(camRight, rayDir));

    float3 linearAlbedo = pow(max(encAlbedo.rgb, 0.0), 2.2);
    float3 shadedHdr = EvaluateLilToonSurface(
        linearAlbedo,
        worldNormal,
        viewVec,
        sunDir,
        sunCol,
        combinedAmbient,
        csmShadow,
        naturalAo,
        globalParams0.y,
        globalParams0.z,
        globalParams0.w,
        globalParams1.x,
        globalParams1.y,
        globalParams1.z,
        lutMask,
        matSlot,
        vtoonMatcapTex,
        vtoonLinearSamp,
        charParams.w,
        camRight,
        camUp
    );

    if (extraParams.w > 0.5) {
        // Optional debug visualization mode via INI debug_mode=1 (show slot ID color)
        shadedHdr = float3((float)slotIdx / 15.0, lutMask.g, lutMask.b);
    }

    return float4(shadedHdr * max(globalScalars3.z, 0.001), 0.0);
}
)HLSL";

inline const char* kVToonForwardAlphaHlsl = R"HLSL(
cbuffer rage_matrices : register(b1) {
    float4x4 worldMtx;
    float4x4 worldViewMtx;
    float4x4 worldViewProjMtx;
    float4x4 viewInverseMtx;
};

cbuffer misc_globals : register(b2) {
    float4 miscPadBefore[11];
    float4 globalScalars;
    float4 globalScalars2;
    float4 globalScalars3;
};

cbuffer lighting_globals : register(b3) {
    float4 gDirectionalLight;
    float4 gDirectionalColour;
    float4 lightPadMid[41];
    float4 gLightNaturalAmbient0;
    float4 gLightNaturalAmbient1;
    float4 gLightArtificialInt0;
    float4 gLightArtificialInt1;
    float4 gLightArtificialExt0;
    float4 gLightArtificialExt1;
    float4 gDirectionalAmbientColour;
};

cbuffer ped_common_shared_locals : register(b13) {
    float4 pedPadBefore[4];
    float4 matColorScale[2];
};

cbuffer VToonGlobalCB : register(b7) {
    float4 globalParams0;
    float4 globalParams1;
    float4 charParams;
    float4 extraParams;
    VToonMaterialData activeMaterials[16];
};

Texture2D diffuseTex          : register(t0);
SamplerState diffuseSamp      : register(s0);
Texture2D vtoonLutTex         : register(t17);
Texture2D vtoonMatcapTex      : register(t18);
SamplerState vtoonLinearSamp  : register(s13);

struct PedAlphaInput {
    float2 texCoord0   : TEXCOORD0;
    float3 worldNormal : TEXCOORD1;
    float4 worldPos    : TEXCOORD2;
    float4 vertColor0  : TEXCOORD3;
    float3 extraPad0   : TEXCOORD4;
    float3 worldTan    : TEXCOORD5;
    float3 worldBitan  : TEXCOORD6;
    float4 svPosition  : SV_Position;
    float4 clipDist    : SV_ClipDistance;
    bool isFrontFace   : SV_IsFrontFace;
};

float4 MainForwardAlpha(PedAlphaInput inputData) : SV_Target0 {
    float4 texSample = diffuseTex.Sample(diffuseSamp, inputData.texCoord0);
    float finalAlpha = saturate(texSample.a * inputData.vertColor0.a * globalScalars.x * globalParams1.w);
    if (finalAlpha < 0.008) {
        discard;
    }

    float3 surfNormal = normalize(inputData.worldNormal);
    if (!inputData.isFrontFace) {
        surfNormal = -surfNormal;
    }
    float3 viewVec = normalize(viewInverseMtx[3].xyz - inputData.worldPos.xyz);

    float4 lutMask = float4(0.333, 1.0, 0.6, 0.0);
    if (charParams.z > 0.5) {
        lutMask = vtoonLutTex.SampleLevel(vtoonLinearSamp, inputData.texCoord0, 0);
    }
    int slotIdx = clamp((int)round(lutMask.r * 15.0), 0, 15);
    VToonMaterialData matSlot = activeMaterials[slotIdx];

    float ambFactor = max(0.0, surfNormal.z + gLightNaturalAmbient0.w) * gLightNaturalAmbient1.w;
    float3 natBase = gLightNaturalAmbient0.xyz * ambFactor + gLightNaturalAmbient1.xyz;
    float3 extAmb = gLightArtificialExt0.xyz * ambFactor + gLightArtificialExt1.xyz;
    float3 dirAxis = float3(gLightArtificialInt1.w, gLightArtificialExt0.w, gLightArtificialExt1.w);
    float3 combinedAmbient = natBase + gDirectionalAmbientColour.xyz * saturate(dot(dirAxis, surfNormal)) + extAmb * 0.5;

    float3 sunDir = normalize(-gDirectionalLight.xyz);
    float3 sunCol = max(gDirectionalColour.xyz, float3(0.0, 0.0, 0.0));
    float3 camRight = normalize(viewInverseMtx[0].xyz);
    float3 camUp = normalize(viewInverseMtx[1].xyz);

    float3 linearAlbedo = pow(max(texSample.rgb * matColorScale[0].x, 0.0), 2.2);
    float3 shadedHdr = EvaluateLilToonSurface(
        linearAlbedo,
        surfNormal,
        viewVec,
        sunDir,
        sunCol,
        combinedAmbient,
        1.0,
        1.0,
        globalParams0.y,
        globalParams0.z,
        globalParams0.w,
        globalParams1.x,
        globalParams1.y,
        globalParams1.z,
        lutMask,
        matSlot,
        vtoonMatcapTex,
        vtoonLinearSamp,
        charParams.w,
        camRight,
        camUp
    );

    return float4(shadedHdr * max(globalScalars3.z, 0.001), finalAlpha);
}
)HLSL";

}  // namespace gtav_vtoon
