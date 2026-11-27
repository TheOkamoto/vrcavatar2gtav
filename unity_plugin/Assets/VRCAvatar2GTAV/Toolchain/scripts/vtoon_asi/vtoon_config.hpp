#pragma once
/*
 * vtoon_config.hpp
 * ================
 * Layer 1 (Configuration, Material Tables & WIC Texture Loading): Defines
 * per-material lilToon parameters (`VToonMaterialSlot`), per-character profiles
 * (`VToonCharacterProfile`), PNG-to-ID3D11ShaderResourceView loading via Windows
 * Imaging Component (WIC), and live hot-reloadable `GTAVVToon.ini` parsing.
 */

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d11.h>
#include <wincodec.h>

#include <cctype>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <mutex>
#include <sstream>
#include <string>
#include <vector>

namespace gtav_vtoon {

constexpr int kMaxVToonCharacters = 16;
constexpr int kMaxVToonMaterialSlots = 16;
constexpr float kMinLumDefault = 0.25f;
constexpr float kMaxLumDefault = 0.86f;

/** Unpacked GPU-ready per-material lilToon shading parameters (16 floats x 6 rows = 96 bytes? -> 6 float4s). */
struct alignas(16) VToonGpuMaterial {
    float colorTint[4];        // rgb = _Color linear/tint, w = cutoff
    float shadowColor[4];      // rgb = _ShadowColor, w = _ShadowBorder
    float shadow2ndColor[4];   // rgb = _Shadow2ndColor, w = _ShadowBlur
    float shadowBorderColor[4];// rgb = _ShadowBorderColor, w = _ShadowBorderRange
    float rimColor[4];         // rgb = _RimColor, w = _RimBorder
    float matcapColor[4];      // rgb = _MatCapColor, w = _MatCapBlend
    float tuningA[4];          // x=_ShadowStrength, y=_Shadow2ndBorder, z=_Shadow2ndBlur, w=_ShadowReceive
    float tuningB[4];          // x=_LightMinLimit, y=_LightMaxLimit, z=_RimBlur, w=_RimFresnelPower
    float tuningC[4];          // x=_RimMainStrength, y=_RimEnable, z=_MatCapEnable, w=_SpecularIntensity
    float flagsMisc[4];        // x=slotType(0=cloth,1=skin,2=face,3=eyes,4=hair,5=hairAlpha,6=nails,7=metal), y=doubleSided, z=lutIndex, w=reserved
};

/** Global VToon lighting & exposure constants passed in constant buffer `b7` / `b9`. */
struct alignas(16) VToonGpuGlobalCB {
    float globalParams0[4];    // x=enabled, y=daylightScale, z=minWorldLum, w=maxWorldLum
    float globalParams1[4];    // x=sunSoftCap, y=ambientBoost, z=shadowScale, w=alphaBoost
    float charParams[4];       // x=activeCharId, y=activeSlotMask, z=hasLut, w=hasMatcap
    float extraParams[4];      // x=screenWidth, y=screenHeight, z=sampleCount, w=debugMode
    VToonGpuMaterial activeMaterials[kMaxVToonMaterialSlots];
};

/** Global VToon draw-call override constants passed in `b9` for GBuffer / ForwardAlpha. */
struct alignas(16) VToonDrawCB {
    float drawCharInfo[4];     // x=encodedCharId, y=cutoff, z=alphaScale, w=doubleSided
    float drawTint[4];         // rgb=colorTint, w=isCutout
    VToonGpuMaterial forwardSlot;
};

/** Loaded CPU-side character profile including paths to UV LUT and MatCap PNGs. */
struct VToonCharacterProfile {
    int charId = 1;
    std::string name;
    std::string lutPngPath;
    std::string matcapPngPath;
    std::vector<VToonGpuMaterial> slots;
    ID3D11ShaderResourceView* lutSrv = nullptr;
    ID3D11ShaderResourceView* matcapSrv = nullptr;
    bool matcapIsAtlas = false;
    bool texturesAttempted = false;
};

/** Top-level runtime configuration synchronized across threads. */
struct VToonRuntimeConfig {
    bool enabled = true;
    int debugMode = 0;
    float daylightScale = 0.94f;
    float minWorldLum = kMinLumDefault;
    float maxWorldLum = kMaxLumDefault;
    float sunSoftCap = 0.96f;
    float ambientBoost = 1.00f;
    float shadowScale = 0.85f;
    float alphaBoost = 1.0f;
    std::vector<VToonCharacterProfile> characters;
};

inline std::mutex& GetVToonLogMutex() {
    static std::mutex logMutex;
    return logMutex;
}

inline std::string GetModuleDirectoryA() {
    char bufPath[MAX_PATH] = {};
    HMODULE modHandle = nullptr;
    GetModuleHandleExA(
        GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCSTR>(&GetModuleDirectoryA),
        &modHandle
    );
    GetModuleFileNameA(modHandle, bufPath, MAX_PATH);
    std::string fullStr(bufPath);
    size_t slashPos = fullStr.find_last_of("\\/");
    return (slashPos != std::string::npos) ? fullStr.substr(0, slashPos) : ".";
}

inline void LogVToonMessage(const std::string& msgText) {
    std::lock_guard<std::mutex> lockGuard(GetVToonLogMutex());
    std::string logPath = GetModuleDirectoryA() + "\\GTAVVToon.log";
    FILE* fileHandle = std::fopen(logPath.c_str(), "a");
    if (fileHandle) {
        std::fprintf(fileHandle, "[VToon] %s\n", msgText.c_str());
        std::fclose(fileHandle);
    }
}

inline void ResetVToonLogFile() {
    std::lock_guard<std::mutex> lockGuard(GetVToonLogMutex());
    std::string logPath = GetModuleDirectoryA() + "\\GTAVVToon.log";
    FILE* fileHandle = std::fopen(logPath.c_str(), "w");
    if (fileHandle) {
        std::fprintf(fileHandle, "[VToon] Log initialized\n");
        std::fclose(fileHandle);
    }
}

inline std::string TrimWhitespace(const std::string& rawStr) {
    size_t startIdx = 0;
    while (startIdx < rawStr.size() && std::isspace(static_cast<unsigned char>(rawStr[startIdx]))) {
        startIdx++;
    }
    size_t endIdx = rawStr.size();
    while (endIdx > startIdx && std::isspace(static_cast<unsigned char>(rawStr[endIdx - 1]))) {
        endIdx--;
    }
    return rawStr.substr(startIdx, endIdx - startIdx);
}

inline std::string ToLowerAscii(std::string inputStr) {
    for (char& charVal : inputStr) {
        charVal = static_cast<char>(std::tolower(static_cast<unsigned char>(charVal)));
    }
    return inputStr;
}

inline VToonGpuMaterial MakeDefaultMaterialSlot() {
    VToonGpuMaterial mat{};
    mat.colorTint[0] = 1.0f;
    mat.colorTint[1] = 1.0f;
    mat.colorTint[2] = 1.0f;
    mat.colorTint[3] = 0.001f;
    mat.shadowColor[0] = 0.85f;
    mat.shadowColor[1] = 0.80f;
    mat.shadowColor[2] = 0.84f;
    mat.shadowColor[3] = 0.50f;
    mat.shadow2ndColor[0] = 0.78f;
    mat.shadow2ndColor[1] = 0.76f;
    mat.shadow2ndColor[2] = 0.82f;
    mat.shadow2ndColor[3] = 0.17f;
    mat.shadowBorderColor[0] = 1.0f;
    mat.shadowBorderColor[1] = 0.75f;
    mat.shadowBorderColor[2] = 0.82f;
    mat.shadowBorderColor[3] = 0.08f;
    mat.rimColor[0] = 0.75f;
    mat.rimColor[1] = 0.75f;
    mat.rimColor[2] = 0.80f;
    mat.rimColor[3] = 0.50f;
    mat.matcapColor[0] = 1.0f;
    mat.matcapColor[1] = 1.0f;
    mat.matcapColor[2] = 1.0f;
    mat.matcapColor[3] = 0.50f;
    mat.tuningA[0] = 1.0f;  // shadowStrength
    mat.tuningA[1] = 0.38f; // shadow2ndBorder
    mat.tuningA[2] = 0.30f; // shadow2ndBlur
    mat.tuningA[3] = 0.65f; // shadowReceive
    mat.tuningB[0] = 0.12f; // lightMinLimit
    mat.tuningB[1] = 1.00f; // lightMaxLimit
    mat.tuningB[2] = 0.15f; // rimBlur
    mat.tuningB[3] = 2.50f; // rimFresnelPower
    mat.tuningC[0] = 0.25f; // rimMainStrength
    mat.tuningC[1] = 1.0f;  // rimEnable
    mat.tuningC[2] = 0.0f;  // matcapEnable
    mat.tuningC[3] = 0.0f;  // specularIntensity
    mat.flagsMisc[3] = 0.0f; // anisotropy
    return mat;
}

inline void ParseVec4Field(const std::string& rawVal, float outArr[4], int countMax = 4) {
    std::string cleaned = rawVal;
    for (char& chItem : cleaned) {
        if (chItem == ',') {
            chItem = ' ';
        }
    }
    std::istringstream strStream(cleaned);
    for (int idx = 0; idx < countMax; ++idx) {
        float parsedVal = 0.0f;
        if (!(strStream >> parsedVal)) {
            break;
        }
        outArr[idx] = parsedVal;
    }
}

inline bool LoadVToonIniConfig(const std::string& iniPath, VToonRuntimeConfig& outConfig) {
    std::ifstream iniFile(iniPath);
    if (!iniFile.is_open()) {
        return false;
    }

    VToonRuntimeConfig parsedCfg{};
    std::string curSection;
    VToonCharacterProfile* curCharPtr = nullptr;
    VToonGpuMaterial* curMatPtr = nullptr;

    std::string lineTxt;
    while (std::getline(iniFile, lineTxt)) {
        size_t semiPos = lineTxt.find(';');
        if (semiPos != std::string::npos) {
            lineTxt.resize(semiPos);
        }
        size_t hashPos = lineTxt.find('#');
        if (hashPos != std::string::npos) {
            lineTxt.resize(hashPos);
        }
        std::string trimmed = TrimWhitespace(lineTxt);
        if (trimmed.empty()) {
            continue;
        }
        if (trimmed.front() == '[' && trimmed.back() == ']') {
            curSection = TrimWhitespace(trimmed.substr(1, trimmed.size() - 2));
            curCharPtr = nullptr;
            curMatPtr = nullptr;
            std::string lowSec = ToLowerAscii(curSection);
            if (lowSec.rfind("char_", 0) == 0) {
                VToonCharacterProfile prof{};
                prof.charId = std::atoi(lowSec.c_str() + 5);
                if (prof.charId < 1) {
                    prof.charId = static_cast<int>(parsedCfg.characters.size()) + 1;
                }
                prof.slots.assign(kMaxVToonMaterialSlots, MakeDefaultMaterialSlot());
                parsedCfg.characters.push_back(prof);
                curCharPtr = &parsedCfg.characters.back();
            } else if (lowSec.rfind("mat_", 0) == 0) {
                int parsedCharId = 0;
                int parsedSlotId = 0;
                if (std::sscanf(lowSec.c_str(), "mat_%d_%d", &parsedCharId, &parsedSlotId) == 2) {
                    for (VToonCharacterProfile& itemProf : parsedCfg.characters) {
                        if (itemProf.charId == parsedCharId && parsedSlotId >= 0 &&
                            parsedSlotId < kMaxVToonMaterialSlots) {
                            curMatPtr = &itemProf.slots[static_cast<size_t>(parsedSlotId)];
                            break;
                        }
                    }
                }
            }
            continue;
        }

        size_t eqPos = trimmed.find('=');
        if (eqPos == std::string::npos) {
            continue;
        }
        std::string keyStr = ToLowerAscii(TrimWhitespace(trimmed.substr(0, eqPos)));
        std::string valStr = TrimWhitespace(trimmed.substr(eqPos + 1));

        if (ToLowerAscii(curSection) == "global") {
            if (keyStr == "enabled") parsedCfg.enabled = (std::atoi(valStr.c_str()) != 0);
            else if (keyStr == "debug_mode") parsedCfg.debugMode = std::atoi(valStr.c_str());
            else if (keyStr == "daylight_scale") parsedCfg.daylightScale = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "min_world_lum") parsedCfg.minWorldLum = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "max_world_lum") parsedCfg.maxWorldLum = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "sun_soft_cap") parsedCfg.sunSoftCap = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "ambient_boost") parsedCfg.ambientBoost = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "shadow_scale") parsedCfg.shadowScale = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "alpha_boost") parsedCfg.alphaBoost = std::strtof(valStr.c_str(), nullptr);
        } else if (curCharPtr != nullptr) {
            if (keyStr == "name") curCharPtr->name = valStr;
            else if (keyStr == "lut_png") curCharPtr->lutPngPath = valStr;
            else if (keyStr == "matcap_png") curCharPtr->matcapPngPath = valStr;
        } else if (curMatPtr != nullptr) {
            if (keyStr == "color") ParseVec4Field(valStr, curMatPtr->colorTint, 3);
            else if (keyStr == "cutoff") curMatPtr->colorTint[3] = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "shadow_color") ParseVec4Field(valStr, curMatPtr->shadowColor, 3);
            else if (keyStr == "shadow_border") curMatPtr->shadowColor[3] = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "shadow_2nd_color") ParseVec4Field(valStr, curMatPtr->shadow2ndColor, 3);
            else if (keyStr == "shadow_blur") curMatPtr->shadow2ndColor[3] = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "shadow_border_color") ParseVec4Field(valStr, curMatPtr->shadowBorderColor, 3);
            else if (keyStr == "shadow_border_range") curMatPtr->shadowBorderColor[3] = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "rim_color") ParseVec4Field(valStr, curMatPtr->rimColor, 3);
            else if (keyStr == "rim_border") curMatPtr->rimColor[3] = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "matcap_color") ParseVec4Field(valStr, curMatPtr->matcapColor, 4);
            else if (keyStr == "shadow_strength") curMatPtr->tuningA[0] = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "shadow_2nd_border") curMatPtr->tuningA[1] = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "shadow_2nd_blur") curMatPtr->tuningA[2] = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "shadow_receive") curMatPtr->tuningA[3] = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "light_min_limit") curMatPtr->tuningB[0] = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "light_max_limit") curMatPtr->tuningB[1] = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "rim_blur") curMatPtr->tuningB[2] = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "rim_fresnel") curMatPtr->tuningB[3] = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "rim_main_strength") curMatPtr->tuningC[0] = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "use_rim") curMatPtr->tuningC[1] = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "use_matcap") curMatPtr->tuningC[2] = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "specular_intensity") curMatPtr->tuningC[3] = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "slot_type") curMatPtr->flagsMisc[0] = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "double_sided") curMatPtr->flagsMisc[1] = std::strtof(valStr.c_str(), nullptr);
            else if (keyStr == "anisotropy") {
                float parsedAniso = std::strtof(valStr.c_str(), nullptr);
                curMatPtr->flagsMisc[3] = (parsedAniso < 0.0f) ? 0.0f : ((parsedAniso > 1.0f) ? 1.0f : parsedAniso);
            }
        }
    }

    outConfig = parsedCfg;
    return !outConfig.characters.empty();
}

inline ID3D11ShaderResourceView* LoadPngFileToSrv(
    ID3D11Device* d3dDevice,
    const std::string& rawRelOrAbsPath,
    bool forcePointOrUnorm = true,
    UINT* outWidth = nullptr
) {
    if (!d3dDevice || rawRelOrAbsPath.empty()) {
        return nullptr;
    }
    std::string resolvedPath = rawRelOrAbsPath;
    if (resolvedPath.size() < 2 || (resolvedPath[1] != ':' && resolvedPath[0] != '\\' && resolvedPath[0] != '/')) {
        resolvedPath = GetModuleDirectoryA() + "\\" + resolvedPath;
    }
    int wideLen = MultiByteToWideChar(CP_UTF8, 0, resolvedPath.c_str(), -1, nullptr, 0);
    if (wideLen <= 0) {
        return nullptr;
    }
    std::wstring widePath(static_cast<size_t>(wideLen), wchar_t(0));
    MultiByteToWideChar(CP_UTF8, 0, resolvedPath.c_str(), -1, &widePath[0], wideLen);

    HRESULT comRes = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    IWICImagingFactory* wicFactory = nullptr;
    HRESULT factoryRes = CoCreateInstance(
        CLSID_WICImagingFactory,
        nullptr,
        CLSCTX_INPROC_SERVER,
        IID_PPV_ARGS(&wicFactory)
    );
    if (FAILED(factoryRes) || !wicFactory) {
        if (SUCCEEDED(comRes)) CoUninitialize();
        return nullptr;
    }

    IWICBitmapDecoder* wicDecoder = nullptr;
    IWICBitmapFrameDecode* wicFrame = nullptr;
    IWICFormatConverter* wicConverter = nullptr;
    ID3D11ShaderResourceView* outSrv = nullptr;

    if (SUCCEEDED(wicFactory->CreateDecoderFromFilename(widePath.c_str(), nullptr, GENERIC_READ, WICDecodeMetadataCacheOnLoad, &wicDecoder)) &&
        wicDecoder &&
        SUCCEEDED(wicDecoder->GetFrame(0, &wicFrame)) &&
        wicFrame &&
        SUCCEEDED(wicFactory->CreateFormatConverter(&wicConverter)) &&
        wicConverter &&
        SUCCEEDED(wicConverter->Initialize(wicFrame, GUID_WICPixelFormat32bppRGBA, WICBitmapDitherTypeNone, nullptr, 0.0, WICBitmapPaletteTypeCustom))) {
        UINT imgWidth = 0;
        UINT imgHeight = 0;
        wicConverter->GetSize(&imgWidth, &imgHeight);
        if (outWidth) *outWidth = imgWidth;
        if (imgWidth > 0 && imgHeight > 0) {
            std::vector<uint8_t> rgbaPixels(static_cast<size_t>(imgWidth) * imgHeight * 4);
            if (SUCCEEDED(wicConverter->CopyPixels(nullptr, imgWidth * 4, static_cast<UINT>(rgbaPixels.size()), rgbaPixels.data()))) {
                D3D11_TEXTURE2D_DESC texDesc{};
                texDesc.Width = imgWidth;
                texDesc.Height = imgHeight;
                texDesc.MipLevels = 1;
                texDesc.ArraySize = 1;
                texDesc.Format = forcePointOrUnorm ? DXGI_FORMAT_R8G8B8A8_UNORM : DXGI_FORMAT_R8G8B8A8_UNORM_SRGB;
                texDesc.SampleDesc.Count = 1;
                texDesc.Usage = D3D11_USAGE_IMMUTABLE;
                texDesc.BindFlags = D3D11_BIND_SHADER_RESOURCE;

                D3D11_SUBRESOURCE_DATA initData{};
                initData.pSysMem = rgbaPixels.data();
                initData.SysMemPitch = imgWidth * 4;

                ID3D11Texture2D* tex2d = nullptr;
                if (SUCCEEDED(d3dDevice->CreateTexture2D(&texDesc, &initData, &tex2d)) && tex2d) {
                    D3D11_SHADER_RESOURCE_VIEW_DESC srvDesc{};
                    srvDesc.Format = texDesc.Format;
                    srvDesc.ViewDimension = D3D11_SRV_DIMENSION_TEXTURE2D;
                    srvDesc.Texture2D.MipLevels = 1;
                    d3dDevice->CreateShaderResourceView(tex2d, &srvDesc, &outSrv);
                    tex2d->Release();
                }
            }
        }
    }

    if (wicConverter) wicConverter->Release();
    if (wicFrame) wicFrame->Release();
    if (wicDecoder) wicDecoder->Release();
    wicFactory->Release();
    if (SUCCEEDED(comRes)) CoUninitialize();
    return outSrv;
}

}  // namespace gtav_vtoon
