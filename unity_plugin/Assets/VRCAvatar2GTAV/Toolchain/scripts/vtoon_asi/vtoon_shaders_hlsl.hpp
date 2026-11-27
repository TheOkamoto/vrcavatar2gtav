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
    float4 miscRaw[16];
};

cbuffer lighting_globals : register(b3) {
    float4 lightPadBefore[45];
    float4 lightIntAmb0;
    float4 lightIntAmb1;
    float4 lightExtAmb0;
    float4 lightExtAmb1;
    float4 dirAmbientColour;
};

cbuffer more_stuff : register(b5) {
    float4 morePadBefore[3];
    float4 gDynamicBakesAndWetness;
};

cbuffer ped_common_shared_locals : register(b13) {
    float4 pedPadBefore[4];
    float4 matColorScale[2];
};

cbuffer ped_common_locals2 : register(b10) {
    float pedBumpiness;
    float pedSpecFresnel;
    float pedSpecFalloff;
    float pedSpecIntMult;
};

cbuffer VToonDrawCB : register(b9) {
    float4 drawCharInfo;
    float4 drawTint;
    float4 drawSlotPad[10];
};

Texture2D diffuseTex : register(t0);
SamplerState diffuseSamp : register(s0);
#ifdef VTOON_PED_STD
Texture2D pedBumpTex : register(t3);
SamplerState pedBumpSamp : register(s3);
Texture2D pedSpecTex : register(t4);
SamplerState pedSpecSamp : register(s4);
#endif

struct PedGbufInput {
    float4 svPosition  : SV_Position;
    float2 texCoord0   : TEXCOORD0;
    float3 worldNormal : TEXCOORD1;
    float4 vertColor0  : TEXCOORD3;
#ifdef VTOON_PED_STD
    float3 extraTex4   : TEXCOORD4;
    float3 worldTan    : TEXCOORD5;
    float3 worldBitan  : TEXCOORD6;
#endif
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

PedGbufOutput MainPedGBuffer(PedGbufInput inputData) {
    int miscIdx = (drawCharInfo.w > 0.5) ? 12 : 11;
    float4 globalScalars = miscRaw[miscIdx];
    float4 globalScalars2 = miscRaw[miscIdx + 1];

    float4 texSample = diffuseTex.Sample(diffuseSamp, inputData.texCoord0);
    float fadeAlpha = inputData.vertColor0.a * globalScalars.x;
    float effectiveAlpha = texSample.a * fadeAlpha;
    if (drawTint.w > 0.5 && effectiveAlpha < drawCharInfo.y) {
        discard;
    }

    float3 surfNormal = normalize(inputData.worldNormal);
    float gbufSpecInt = 0.0;
    float gbufSpecExp = 0.04;
    float gbufSpecFres = 0.98;
#ifdef VTOON_PED_STD
    float3 bumpRaw = pedBumpTex.Sample(pedBumpSamp, inputData.texCoord0).xyz;
    float2 bumpXy = (bumpRaw.xy * 2.0 - 1.0) * clamp(pedBumpiness, 0.0, 1.5);
    float bumpZ = sqrt(max(1.0 - saturate(dot(bumpXy, bumpXy)), 0.01));
    float3 perturbedN = surfNormal * bumpZ + inputData.worldTan * bumpXy.x + inputData.worldBitan * bumpXy.y + inputData.extraTex4 * 1e-6;
    if (pedBumpiness > 0.01 && dot(perturbedN, perturbedN) > 0.05) {
        surfNormal = normalize(perturbedN);
    }
    float3 specSample = pedSpecTex.Sample(pedSpecSamp, inputData.texCoord0).rgb;
    gbufSpecInt = saturate(specSample.r * clamp(pedSpecIntMult, 0.0, 1.0));
    gbufSpecExp = saturate(specSample.g * clamp(pedSpecFalloff * (1.0 / 512.0), 0.02, 1.0));
    gbufSpecFres = clamp(pedSpecFresnel, 0.5, 0.99);
#endif

    float extraNormalBits = 0.0;
    float3 encodedNormal = EncodeGtaWorldNormal(surfNormal, extraNormalBits);

    float ambientZ = saturate(surfNormal.z * 0.5 + 0.5);
    float vertAo = max(inputData.vertColor0.r, 0.25);
    float hemiNat = (abs(gDynamicBakesAndWetness.x) + abs(gDynamicBakesAndWetness.y) > 0.001)
        ? saturate(ambientZ * gDynamicBakesAndWetness.y + gDynamicBakesAndWetness.x)
        : saturate(ambientZ * 0.65 + 0.35);
    float naturalAo = saturate(vertAo * globalScalars.z * hemiNat + lightIntAmb0.w);
    float artGate = saturate(globalScalars2.z + dirAmbientColour.w);
    float artAo = saturate(vertAo * globalScalars.y * (ambientZ + 0.3) * max(artGate, 0.25));

    PedGbufOutput outputData;
    outputData.targetAlbedo = float4(saturate(texSample.rgb * matColorScale[0].x), saturate(effectiveAlpha));
    outputData.targetNormal = float4(encodedNormal, extraNormalBits);
    outputData.targetSpec   = float4(sqrt(gbufSpecInt), sqrt(gbufSpecExp), gbufSpecFres, 1.0);
    // Keep emissive zeroed (.z=0) and .w=0.51 so blurry SSS is skipped without chrome env reflection
    outputData.targetAoEm   = float4(sqrt(naturalAo * 0.5), sqrt(artAo * 0.5), 0.0, 0.51);
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
    float3 camUpVec,
    float specMask
) {
    float3 tintedAlbedo = albedoLinear * matSlot.colorTint.rgb;

    // Preserve real physical GTA V HDR radiance scale while compressing extreme sun-to-ambient contrast
    float3 lumaWeights = float3(0.2126, 0.7152, 0.0722);
    float3 boostAmbient = ambientColor * ambientBoost;
    float ambLum = max(dot(boostAmbient, lumaWeights), 1e-4);
    float sunLumRaw = max(dot(sunColor, lumaWeights), 0.0);
    float sunRatio = sunLumRaw / max(ambLum, 0.04);
    float sunCompress = 1.0 / (1.0 + sunRatio * (0.08 / max(sunSoftCap, 0.35)));
    float3 softSun = sunColor * sunCompress;
    float3 totalIncident = boostAmbient + softSun * lerp(0.18, 0.72, csmShadow);
    float rawLum = max(dot(totalIncident, lumaWeights), 1e-4);
    float3 balancedIncident = lerp(totalIncident, float3(rawLum, rawLum, rawLum), 0.30);
    float balLum = max(dot(balancedIncident, lumaWeights), 1e-4);
    float refLum = max(ambLum, balLum);
    float relMin = refLum * max(minWorldLum * 0.55, matSlot.tuningB.x * 0.55);
    float relMax = max(ambLum * 3.8, refLum * max(maxWorldLum, matSlot.tuningB.y * 1.25));
    float clampedLum = clamp(balLum * daylightScale, relMin, relMax);
    float3 lightColor = (balancedIncident / balLum) * clampedLum;

    // Weight directional Half-Lambert by real sun-vs-ambient strength so interiors shade smoothly
    float dotNL = dot(worldNorm, sunDir);
    float halfLambert = saturate(dotNL * 0.5 + 0.5);
    float sunLum = dot(softSun, lumaWeights);
    float dirStrength = saturate(sunLum / max(sunLum + ambLum * 0.85, 1e-4));
    float hemiShade = saturate(worldNorm.z * 0.30 + 0.70);
    float directionalShade = lerp(hemiShade, halfLambert, dirStrength);
    float csmWeight = lerp(1.0, csmShadow, saturate(matSlot.tuningA.w * shadowScale * dirStrength));
    float shadeInput = directionalShade * csmWeight * lerp(0.88, 1.0, naturalAo);

    float step1 = ComputeTooningStep(shadeInput, matSlot.shadowColor.w, matSlot.shadow2ndColor.w);
    float step2 = ComputeTooningStep(shadeInput, matSlot.tuningA.y, matSlot.tuningA.z);

    // Subtle colored SSS terminator border right along the 1st cel transition (disabled when range == 0)
    float borderFactor = 0.0;
    if (matSlot.shadowBorderColor.w > 0.001) {
        float borderSpan = max(matSlot.shadowBorderColor.w, 0.02);
        borderFactor = saturate(1.0 - abs(shadeInput - matSlot.shadowColor.w) / borderSpan);
    }

    float shadowMaskWeight = saturate(matSlot.tuningA.x * lutMaskSample.g);
    float3 colSh1 = tintedAlbedo * lerp(float3(1.0, 1.0, 1.0), matSlot.shadowColor.rgb, shadowMaskWeight);
    colSh1 = lerp(colSh1, colSh1 * matSlot.shadowBorderColor.rgb, borderFactor * 0.65);
    float3 colSh2 = tintedAlbedo * lerp(float3(1.0, 1.0, 1.0), matSlot.shadow2ndColor.rgb, shadowMaskWeight * 0.85);
    // Match lilToon `indirectCol = min(indirectCol, directCol)` so deep shadow2 never lightens into cyan patches
    colSh2 = min(colSh2, colSh1);

    float3 shadowedAlbedo = lerp(colSh2, colSh1, step2);
    float3 baseCelAlbedo = lerp(shadowedAlbedo, tintedAlbedo, step1);

    float3 outColor = baseCelAlbedo * lightColor;
    bool isSkinSlot = (matSlot.flagsMisc.x > 0.5 && matSlot.flagsMisc.x < 1.5);
    bool isFaceSlot = (matSlot.flagsMisc.x > 1.5 && matSlot.flagsMisc.x < 2.5);
    bool isSkinOrFace = (isSkinSlot || isFaceSlot);
    bool isHairSlot = (matSlot.flagsMisc.x > 3.5 && matSlot.flagsMisc.x < 5.5);

    // Soft diffuse blowout compression on skin/face proportional to physical scene radiance
    if (isSkinOrFace) {
        float skinCap = clampedLum * max(matSlot.tuningB.y * 1.35, 1.15);
        float3 skinExcess = max(outColor - skinCap * 0.85, 0.0);
        outColor = min(outColor, skinCap * 0.85) + skinExcess / (1.0 + skinExcess / max(skinCap * 0.90, 0.25));
    }

    // View-space Rim Light (subtle contour glow on oily skin, shadow-masked on hair)
    float dotNV = saturate(dot(worldNorm, viewVec));
    if (matSlot.tuningC.y > 0.5) {
        float rimRaw = pow(max(saturate(1.0 - dotNV), 1e-5), max(matSlot.tuningB.w, 0.25));
        float rimStep = ComputeTooningStep(rimRaw, matSlot.rimColor.w, matSlot.tuningB.z);
        float3 rimTint = lerp(matSlot.rimColor.rgb, matSlot.rimColor.rgb * tintedAlbedo, matSlot.tuningC.x);
        float rimScale = isSkinOrFace ? 0.22 : (isHairSlot ? 0.26 * lerp(0.18, 1.0, step1) : 0.35);
        float rimMask = saturate(lutMaskSample.b + (isSkinOrFace ? 0.15 : 0.35));
        outColor += rimTint * rimStep * lightColor * (rimMask * rimScale);
    }

    // View-space MatCap (supports 2x2 role-packed MatCap atlas when hasMatcapTex > 1.5)
    if (matSlot.tuningC.z > 0.5) {
        float2 matcapUv = float2(dot(worldNorm, camRightVec) * 0.5 + 0.5, 0.5 - dot(worldNorm, camUpVec) * 0.5);
        float2 mcSampleUv = matcapUv;
        if (hasMatcapTex > 1.5) {
            float2 quadOff = float2(0.5, 0.5);
            if (isSkinOrFace) quadOff = float2(0.5, 0.0);
            else if (isHairSlot) quadOff = float2(0.0, 0.0);
            else if (matSlot.flagsMisc.x < 0.5 || matSlot.flagsMisc.x > 7.5) quadOff = float2(0.0, 0.5);
            mcSampleUv = clamp(matcapUv, 0.015, 0.985) * 0.5 + quadOff;
        }
        float3 mcSample = float3(1.0, 1.0, 1.0);
        if (hasMatcapTex > 0.5) {
            float3 mcRaw = max(matcapTex.SampleLevel(linearSamp, mcSampleUv, 0).rgb, 1e-5);
            mcSample = isHairSlot ? pow(mcRaw, 1.15) : mcRaw;
        } else {
            float fakeSpec = pow(max(saturate(dot(worldNorm, normalize(viewVec + float3(0.0, 0.0, 0.45)))), 1e-5), 14.0);
            mcSample = float3(fakeSpec, fakeSpec, fakeSpec);
        }
        float mcMask = isSkinSlot
            ? lutMaskSample.b * matSlot.matcapColor.w * ((specMask > 0.01) ? lerp(0.55, 1.0, specMask) : 1.0)
            : lutMaskSample.b * matSlot.matcapColor.w;
        float mcGain = (matSlot.flagsMisc.x > 5.5) ? 0.48
                     : (isSkinSlot ? 0.95 : (isFaceSlot ? 0.45 : (isHairSlot ? 0.55 : 0.25)));
        outColor += mcSample * matSlot.matcapColor.rgb * lightColor * (mcMask * mcGain);
    }

    // Directional & studio top-fill specular sheen driven strictly by Unity _UseReflection / _Specular / _Smoothness / _UseAnisotropy
    if (matSlot.tuningC.w > 0.02) {
        float3 sunHalfRaw = sunDir + viewVec;
        float3 halfSun = (dot(sunHalfRaw, sunHalfRaw) > 1e-5) ? normalize(sunHalfRaw) : worldNorm;
        float3 fillDir = normalize(float3(-sunDir.x * 0.7, -sunDir.y * 0.7, 0.72));
        float3 fillHalfRaw = fillDir + viewVec;
        float3 halfFill = (dot(fillHalfRaw, fillHalfRaw) > 1e-5) ? normalize(fillHalfRaw) : worldNorm;
        float specPow = isSkinOrFace ? lerp(28.0, 72.0, matSlot.tuningC.w) : lerp(18.0, 56.0, matSlot.tuningC.w);
        float lobeSun = pow(max(saturate(dot(worldNorm, halfSun)), 1e-5), specPow) * lerp(0.35, 1.0, csmWeight);
        float lobeFill = pow(max(saturate(dot(worldNorm, halfFill)), 1e-5), specPow * 0.65) * 0.55;
        float specVal = max(lobeSun, lobeFill);
        float anisoVal = saturate(matSlot.flagsMisc.w);
        if (anisoVal > 0.05) {
            float3 upAxis = (abs(worldNorm.z) > 0.998) ? float3(1.0, 0.0, 0.0) : float3(0.0, 0.0, 1.0);
            float3 anisoTan = normalize(cross(worldNorm, upAxis));
            float3 anisoBitan = normalize(cross(anisoTan, worldNorm));
            float alphaT = lerp(0.16, 0.042, anisoVal);
            float alphaB = lerp(0.16, 0.44, anisoVal);
            float htSun = dot(halfSun, anisoTan) / alphaT;
            float hbSun = dot(halfSun, anisoBitan) / alphaB;
            float hnSun = max(dot(worldNorm, halfSun), 0.05);
            float anisoSun = exp(-(htSun * htSun + hbSun * hbSun) / (hnSun * hnSun)) * saturate(dotNL * 0.65 + 0.45) * lerp(0.40, 1.0, csmWeight);
            float htFill = dot(halfFill, anisoTan) / (alphaT * 1.15);
            float hbFill = dot(halfFill, anisoBitan) / (alphaB * 1.15);
            float hnFill = max(dot(worldNorm, halfFill), 0.05);
            float anisoFill = exp(-(htFill * htFill + hbFill * hbFill) / (hnFill * hnFill)) * 0.52;
            specVal = max(specVal, max(anisoSun, anisoFill));
        }
        float fresnelSheen = 0.28 + 0.72 * pow(max(saturate(1.0 - dotNV), 1e-5), 3.0);
        float specMaskScale = (specMask > 0.01) ? lerp(0.45, 1.0, specMask) : 1.0;
        float3 specColor = isSkinOrFace ? lerp(float3(1.0, 0.96, 0.94), tintedAlbedo, 0.15) : lerp(float3(1.0, 1.0, 1.0), tintedAlbedo, 0.25);
        float3 specLight = lightColor * (isSkinSlot ? 1.15 : 1.0);
        float3 specBoost = specColor * specLight * (specVal * fresnelSheen * matSlot.tuningC.w * specMaskScale * (isSkinSlot ? 0.88 : (isHairSlot ? 0.72 : (isFaceSlot ? 0.50 : 0.45))));
        outColor += specBoost;
        if (isSkinOrFace) {
            float oilCeil = clampedLum * 2.15;
            float softStart = clampedLum * 1.55;
            float3 softHead = max(outColor - softStart, 0.0);
            outColor = min(outColor, softStart) + softHead / (1.0 + softHead / max(clampedLum * 0.90, 0.25));
            outColor = min(outColor, float3(oilCeil, oilCeil, oilCeil));
        }
    }

    // Self-illumination / eye highlight & crescent glow protection from LUT alpha mask
    if (lutMaskSample.a > 0.02) {
        float eyeLum = clampedLum * 1.15;
        outColor = max(outColor, tintedAlbedo * eyeLum * saturate(lutMaskSample.a * 1.38));
    }

    return clamp(outColor, float3(0.0, 0.0, 0.0), float3(64.0, 64.0, 64.0));
}
)HLSL";

inline const char* kVToonDeferredOverlayHlsl = R"HLSL(
cbuffer rage_matrices : register(b1) {
    row_major float4x4 worldMtx;
    row_major float4x4 worldViewMtx;
    row_major float4x4 worldViewProjMtx;
    row_major float4x4 viewInverseMtx;
};

cbuffer misc_globals : register(b2) {
    float4 miscRaw[16];
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
Texture2DMS<float4> gBufSpecTex      : register(t9);
Texture2DMS<float4> gBufAoEmTex      : register(t10);
Texture2DMS<uint2>  gBufStencilTex   : register(t11);
Texture2DMS<float>  gBufDepthTex     : register(t12);
Texture2DMS<float4> vtoonMaskTex     : register(t16);
#else
Texture2D gBufAlbedoTex       : register(t7);
Texture2D gBufNormalTex       : register(t8);
Texture2D gBufSpecTex         : register(t9);
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

    int miscIdx = (extraParams.z >= 3.5) ? 12 : 11;
    float4 globalScalars2 = miscRaw[miscIdx + 1];
    float4 globalScalars3 = miscRaw[miscIdx + 2];

    bool hasValidDepth = (extraParams.x > 0.5);
    bool hasShadowTex = (extraParams.y > 0.5);
    bool hasSpecTex = (fmod(floor(extraParams.z + 0.5), 2.0) > 0.5);
    bool hasStencilTex = (fmod(floor(extraParams.z * 0.5 + 0.1), 2.0) > 0.5);

    int2 pxCoord = int2(inputData.svPosition.xy);
#ifdef VTOON_MSAA
    float4 maskSample = vtoonMaskTex.Load(pxCoord, inputData.sampleIndex);
#else
    float4 maskSample = vtoonMaskTex.Load(int3(pxCoord, 0));
#endif

    // Reject untouched pixels always, and depth-test only when t12 is bound for this directional pass
    if (maskSample.x < 0.5 || abs(maskSample.x - charParams.x) > 0.25) {
        discard;
    }
    if (hasValidDepth) {
#ifdef VTOON_MSAA
        float sceneDepth = gBufDepthTex.Load(pxCoord, inputData.sampleIndex).x;
#else
        float sceneDepth = gBufDepthTex.Load(int3(pxCoord, 0)).x;
#endif
        if (sceneDepth > 0.00001 && abs(sceneDepth - maskSample.y) > 0.0015) {
            discard;
        }
    }

#ifdef VTOON_MSAA
    float4 encAlbedo = gBufAlbedoTex.Load(pxCoord, inputData.sampleIndex);
    float4 encNormal = gBufNormalTex.Load(pxCoord, inputData.sampleIndex);
    float4 encSpec   = hasSpecTex ? gBufSpecTex.Load(pxCoord, inputData.sampleIndex) : float4(0.0, 0.0, 0.0, 0.0);
    float4 encAoEm   = gBufAoEmTex.Load(pxCoord, inputData.sampleIndex);
    uint stencilVal  = hasStencilTex ? gBufStencilTex.Load(pxCoord, inputData.sampleIndex).y : 0u;
#else
    float4 encAlbedo = gBufAlbedoTex.Load(int3(pxCoord, 0));
    float4 encNormal = gBufNormalTex.Load(int3(pxCoord, 0));
    float4 encSpec   = hasSpecTex ? gBufSpecTex.Load(int3(pxCoord, 0)) : float4(0.0, 0.0, 0.0, 0.0);
    float4 encAoEm   = gBufAoEmTex.Load(int3(pxCoord, 0));
    uint stencilVal  = hasStencilTex ? gBufStencilTex.Load(int3(pxCoord, 0)).y : 0u;
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
    bool isInterior = hasStencilTex ? ((stencilVal & 8u) != 0u) : (globalScalars2.z > 0.5);
    float3 dirAxis = float3(gLightArtificialInt1.w, gLightArtificialExt0.w, gLightArtificialExt1.w);
    float3 skyAmb = gDirectionalAmbientColour.xyz * saturate(dot(dirAxis, worldNormal)) + natBase;
    float ssaoVal = hasShadowTex ? saturate(gDeferredShadowTex.SampleLevel(gShadowSamp, screenUv, 0).x) : 1.0;
    float ssaoMod = lerp(0.78, 1.0, ssaoVal);
    float natTmp = saturate(encAoEm.x * encAoEm.x * 2.0);
    float artTmp = saturate(encAoEm.y * encAoEm.y * 2.0);
    float naturalAo = natTmp * natTmp;
    float artAo = artTmp * artTmp;
    float3 artAmb = (isInterior ? intAmb : extAmb) * (artAo * ssaoMod);
    float3 combinedAmbient = artAmb + skyAmb * (naturalAo * ssaoMod);

    float csmShadow = hasSpecTex ? saturate(encSpec.w) : (isInterior ? 0.0 : 1.0);
    float sunGate = isInterior ? 0.0 : saturate(natTmp * 3.0);
    float3 sunDir = normalize(float3(0.35, -0.45, 0.82));
    float3 sunCol = float3(0.0, 0.0, 0.0);
    if (charParams.y > 0.5) {
        float3 rawSunDir = -deferredLightParams[1].xyz;
        if (dot(rawSunDir, rawSunDir) > 1e-5) {
            sunDir = normalize(rawSunDir);
        }
        sunCol = max(deferredLightParams[3].xyz, float3(0.0, 0.0, 0.0)) * sunGate;
    }

    float3 camRight = normalize(cross(rayDir, float3(0.0, 0.0, 1.0) + float3(1e-5, 0.0, 0.0)));
    float3 camUp = normalize(cross(camRight, rayDir));

    float specMaskVal = hasSpecTex ? saturate(encSpec.x * encSpec.x) : 0.0;
    float3 linearAlbedo = max(encAlbedo.rgb, 0.0) * max(encAlbedo.rgb, 0.0);
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
        camUp,
        specMaskVal
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
    row_major float4x4 worldMtx;
    row_major float4x4 worldViewMtx;
    row_major float4x4 worldViewProjMtx;
    row_major float4x4 viewInverseMtx;
};

cbuffer misc_globals : register(b2) {
    float4 miscRaw[16];
};

cbuffer lighting_globals : register(b3) {
    float4 gDirectionalLight;
    float4 gDirectionalColour;
    int4   gForwardLightCount;
    float4 gLightPosInvDistSqr[8];
    float4 gLightDirFalloffExp[8];
    float4 gLightColCapsuleExt[8];
    float4 gLightConeScaleArr[8];
    float4 gLightConeOffsetArr[8];
    float4 gLightNaturalAmbient0;
    float4 gLightNaturalAmbient1;
    float4 gLightArtificialInt0;
    float4 gLightArtificialInt1;
    float4 gLightArtificialExt0;
    float4 gLightArtificialExt1;
    float4 gDirectionalAmbientColour;
};

cbuffer more_stuff : register(b5) {
    float4 morePadBefore[3];
    float4 gDynamicBakesAndWetness;
};

cbuffer csmshader : register(b6) {
    float4 gCsmVars[12];
    float4 gCsmDepthBias;
    float4 gCsmDepthSlopeBias;
    float4 gCsmRes;
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

Texture2D diffuseTex              : register(t0);
SamplerState diffuseSamp          : register(s0);
Texture2D gCsmShadowTex           : register(t15);
SamplerComparisonState gCsmShadowSamp : register(s15);
Texture2D vtoonLutTex             : register(t17);
Texture2D vtoonMatcapTex          : register(t18);
SamplerState vtoonLinearSamp      : register(s13);

struct PedAlphaInput {
    float2 texCoord0   : TEXCOORD0;
    float3 worldNormal : TEXCOORD1;
    float4 worldPos    : TEXCOORD2;
    float4 vertColor0  : TEXCOORD3;
};

float SampleForwardCsmShadow(float3 worldPos) {
    float3 posRelCam = worldPos - viewInverseMtx[3].xyz;
    float3 lightCoord = posRelCam.x * gCsmVars[0].xyz + posRelCam.y * gCsmVars[1].xyz + posRelCam.z * gCsmVars[2].xyz;
    float3 casc0 = lightCoord * gCsmVars[4].xyz + gCsmVars[8].xyz;
    float3 casc1 = lightCoord * gCsmVars[5].xyz + gCsmVars[9].xyz;
    float3 casc2 = lightCoord * gCsmVars[6].xyz + gCsmVars[10].xyz;
    float3 casc3 = lightCoord * gCsmVars[7].xyz + gCsmVars[11].xyz;
    float boundHalf = (1.0 - gCsmRes.z * 1.5) * 0.5;
    int cascIdx = 3;
    float3 chosenCoord = casc3;
    float biasVal = gCsmDepthBias.w;
    if (max(abs(casc2.x), abs(casc2.y)) < boundHalf) { cascIdx = 2; chosenCoord = casc2; biasVal = gCsmDepthBias.z; }
    if (max(abs(casc1.x), abs(casc1.y)) < boundHalf) { cascIdx = 1; chosenCoord = casc1; biasVal = gCsmDepthBias.y; }
    if (max(abs(casc0.x), abs(casc0.y)) < boundHalf) { cascIdx = 0; chosenCoord = casc0; biasVal = gCsmDepthBias.x; }
    float2 sampleUv = float2(chosenCoord.x + 0.5, chosenCoord.y * 0.25 + ((float)cascIdx + 0.5) * 0.25);
    float cmpDepth = chosenCoord.z - biasVal;
    float2 tapStep = gCsmRes.zw;
    float pcfSum = 0.0;
    pcfSum += gCsmShadowTex.SampleCmpLevelZero(gCsmShadowSamp, sampleUv + float2(-0.35, 0.33) * tapStep, cmpDepth);
    pcfSum += gCsmShadowTex.SampleCmpLevelZero(gCsmShadowSamp, sampleUv + float2( 0.52,-0.25) * tapStep, cmpDepth);
    pcfSum += gCsmShadowTex.SampleCmpLevelZero(gCsmShadowSamp, sampleUv + float2(-0.48,-0.24) * tapStep, cmpDepth);
    pcfSum += gCsmShadowTex.SampleCmpLevelZero(gCsmShadowSamp, sampleUv + float2( 0.34, 0.24) * tapStep, cmpDepth);
    float pcfVal = pcfSum * 0.25;
    float rawShadow = pcfVal * pcfVal;
    float camDepth = dot(posRelCam, viewInverseMtx[2].xyz);
    float rangeFade = 1.0 - saturate(camDepth * gCsmVars[0].w + gCsmVars[1].w);
    float edgeMask = saturate(max(abs(casc3.x), abs(casc3.y)) * 15.0 - 6.3);
    float shadowed = min(rawShadow + rangeFade * edgeMask, 1.0);
    float heightFade = sqrt(saturate(worldPos.z * gCsmVars[3].x + gCsmVars[3].y)) * gCsmVars[3].z;
    return saturate(shadowed - heightFade * shadowed);
}

float4 MainForwardAlpha(PedAlphaInput inputData) : SV_Target0 {
    int miscIdx = (extraParams.z >= 3.5) ? 12 : 11;
    float4 globalScalars = miscRaw[miscIdx];
    float4 globalScalars2 = miscRaw[miscIdx + 1];
    float4 globalScalars3 = miscRaw[miscIdx + 2];

    float4 texSample = diffuseTex.Sample(diffuseSamp, inputData.texCoord0);
    float fadeAlpha = inputData.vertColor0.a * globalScalars.x;
    float finalAlpha = saturate(texSample.a * fadeAlpha * globalParams1.w);
    if (finalAlpha < 0.008) {
        discard;
    }

    float3 viewVec = normalize(viewInverseMtx[3].xyz - inputData.worldPos.xyz);
    float3 surfNormal = normalize(inputData.worldNormal);
    if (dot(surfNormal, viewVec) < 0.0) {
        surfNormal = -surfNormal;
    }

    float4 lutMask = float4(0.333, 1.0, 0.6, 0.0);
    if (charParams.z > 0.5) {
        lutMask = vtoonLutTex.SampleLevel(vtoonLinearSamp, inputData.texCoord0, 0);
    }
    int slotIdx = clamp((int)round(lutMask.r * 15.0), 0, 15);
    VToonMaterialData matSlot = activeMaterials[slotIdx];
    bool isHairSlot = (matSlot.flagsMisc.x > 3.5 && matSlot.flagsMisc.x < 5.5);
    if (isHairSlot) {
        float liftedZ = lerp(surfNormal.z, max(surfNormal.z, 0.05), 0.75);
        surfNormal = normalize(float3(surfNormal.xy, liftedZ));
    }

    float ambFactor = max(0.0, surfNormal.z + gLightNaturalAmbient0.w) * gLightNaturalAmbient1.w;
    float3 natBase = gLightNaturalAmbient0.xyz * ambFactor + gLightNaturalAmbient1.xyz;
    float3 intAmb = gLightArtificialInt0.xyz * ambFactor + gLightArtificialInt1.xyz;
    float3 extAmb = gLightArtificialExt0.xyz * ambFactor + gLightArtificialExt1.xyz;
    float natScale = saturate(globalScalars.z);
    float intWeight = saturate(globalScalars2.z);
    float extWeight = 1.0 - intWeight;
    float ambientZ = saturate(surfNormal.z * 0.5 + 0.5);
    if (isHairSlot) {
        ambientZ = max(ambientZ, 0.45);
    }
    float vertAo = max(inputData.vertColor0.r, 0.25);
    float hemiNat = (abs(gDynamicBakesAndWetness.x) + abs(gDynamicBakesAndWetness.y) > 0.001)
        ? saturate(ambientZ * gDynamicBakesAndWetness.y + gDynamicBakesAndWetness.x)
        : saturate(ambientZ * 0.65 + 0.35);
    float natRaw = saturate(vertAo * natScale * hemiNat + gLightArtificialInt0.w);
    float naturalAo = natRaw * natRaw;
    float artGate = saturate(globalScalars2.z + gDirectionalAmbientColour.w);
    float artRaw = saturate(vertAo * globalScalars.y * (ambientZ + 0.3) * max(artGate, 0.25));
    float artAo = artRaw * artRaw;
    float3 dirAxis = float3(gLightArtificialInt1.w, gLightArtificialExt0.w, gLightArtificialExt1.w);
    float3 skyAmb = gDirectionalAmbientColour.xyz * saturate(dot(dirAxis, surfNormal)) + natBase;
    float3 artAmb = lerp(extAmb, intAmb, intWeight) * artAo;
    float3 combinedAmbient = artAmb + skyAmb * naturalAo;

    float3 sunDir = normalize(float3(0.35, -0.45, 0.82));
    if (dot(gDirectionalLight.xyz, gDirectionalLight.xyz) > 1e-5) {
        sunDir = normalize(-gDirectionalLight.xyz);
    }
    float sunGate = extWeight * saturate(natRaw * 3.0);
    float3 sunCol = max(gDirectionalColour.xyz, float3(0.0, 0.0, 0.0)) * (2.05 * sunGate);
    float csmShadow = (extraParams.y > 0.5 && extWeight > 0.05)
        ? SampleForwardCsmShadow(inputData.worldPos.xyz)
        : extWeight;
    float3 rayDir = -viewVec;
    float3 camRight = normalize(cross(rayDir, float3(0.0, 0.0, 1.0) + float3(1e-5, 0.0, 0.0)));
    float3 camUp = normalize(cross(camRight, rayDir));
    float specHairMask = isHairSlot ? 0.55 : 0.0;

    float3 baseRgb = saturate(texSample.rgb * matColorScale[0].x);
    float3 linearAlbedo = baseRgb * baseRgb;
    float3 shadedHdr = EvaluateLilToonSurface(
        linearAlbedo,
        surfNormal,
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
        camUp,
        specHairMask
    );

    float3 localLightAccum = float3(0.0, 0.0, 0.0);
    int numLocalLights = min(max(gForwardLightCount.x, 0), 8);
    for (int lightIdx = 0; lightIdx < numLocalLights; ++lightIdx) {
        float4 posInvR = gLightPosInvDistSqr[lightIdx];
        float4 dirFall = gLightDirFalloffExp[lightIdx];
        float4 colCap = gLightColCapsuleExt[lightIdx];
        float3 deltaVec = posInvR.xyz - inputData.worldPos.xyz;
        if (abs(colCap.w) > 1e-5) {
            float projLen = saturate(dot(-deltaVec, dirFall.xyz) / (colCap.w + 1e-4)) * colCap.w;
            deltaVec = (posInvR.xyz + dirFall.xyz * projLen) - inputData.worldPos.xyz;
        }
        float distSq = dot(deltaVec, deltaVec);
        float3 lightDir = deltaVec * rsqrt(max(distSq, 1e-6));
        float normDist = saturate(1.0 - distSq * posInvR.w);
        float falloff = lerp(dirFall.w, 1.0, normDist);
        float atten = normDist / max(falloff, 1e-4);
        float spotCos = dot(-lightDir, dirFall.xyz);
        float spotFactor = saturate(spotCos * gLightConeScaleArr[lightIdx].x + gLightConeOffsetArr[lightIdx].x);
        float ndlWrap = saturate(dot(surfNormal, lightDir) * 0.75 + 0.25);
        localLightAccum += max(colCap.xyz, float3(0.0, 0.0, 0.0)) * (atten * spotFactor * ndlWrap);
    }
    shadedHdr = clamp(shadedHdr + clamp(linearAlbedo * matSlot.colorTint.rgb * localLightAccum, 0.0, 24.0), 0.0, 64.0);

    return float4(shadedHdr * max(globalScalars3.z, 0.001), finalAlpha);
}
)HLSL";

}  // namespace gtav_vtoon
