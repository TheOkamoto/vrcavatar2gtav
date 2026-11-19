/*
 * gtav_physbones.cpp
 * ==================
 * GTA V Legacy ASI plugin (ScriptHookV) porting VRChat VRCPhysBone secondary
 * motion onto custom RAGE crSkeleton chains (starting with Michael's neko mimi
 * articulated ear bones PB_Ear_L_0..2 and PB_Ear_R_0..2).
 *
 * Dynamically binds ScriptHookV.dll at runtime, resolves rage::crSkeleton and
 * rage::crSkeletonData safely via per-pointer SEH reads + injected-bone
 * spatial fingerprinting, and runs a sub-frame sync thread alongside an
 * underdamped filtered Verlet solver so ears bounce naturally while running.
 */

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

namespace {

constexpr float kPi = 3.14159265358979323846f;
constexpr int kMaxBonesPerChain = 16;
constexpr int kMaxSyncNodes = 256;
constexpr int kMaxTrackedPeds = 8;
constexpr int kMaxWorldPedsScan = 256;
constexpr int kRescanCooldownFrames = 30;
constexpr int kSkelHeadTag = 31086;
constexpr int kMaxBlinkBonesPerProfile = 8;

// ScriptHookV native hashes (verified present in ScriptHookV.dll)
constexpr uint64_t kNativePlayerPedId = 0xD80958FC74E988A6ULL;
constexpr uint64_t kNativeGetEntityModel = 0x9F47B058362C84B5ULL;
constexpr uint64_t kNativeGetEntityCoords = 0x3FEF770D40960D5AULL;
constexpr uint64_t kNativeDoesEntityExist = 0x7239B21A38F536BAULL;
constexpr uint64_t kNativeIsEntityDead = 0x5F9532F3B5CC2551ULL;
constexpr uint64_t kNativeGetPedBoneIndex = 0x3F428D08BE5AAE31ULL;
constexpr uint64_t kNativeGetPedBoneCoords = 0x17C07FC640E86B4EULL;
constexpr uint64_t kNativeGetEntityBoneIndexByName = 0xFB71170B7E76ACBAULL;
constexpr uint64_t kNativeGetWorldPositionOfEntityBone = 0x44A8FCB8ED227738ULL;

struct Vec3 {
    float x;
    float y;
    float z;
};

struct Quat {
    float x;
    float y;
    float z;
    float w;
};

struct alignas(16) Mat34V {
    float col0[4];
    float col1[4];
    float col2[4];
    float col3[4];
};

// ScriptHookV native return vector has 8-byte aligned lanes
struct ScriptVector3 {
    float x;
    uint32_t pad0;
    float y;
    uint32_t pad1;
    float z;
    uint32_t pad2;
};

using FnScriptRegister = void (*)(HMODULE, void (*)());
using FnScriptUnregister = void (*)(HMODULE);
using FnScriptWait = void (*)(DWORD);
using FnNativeInit = void (*)(uint64_t);
using FnNativePush64 = void (*)(uint64_t);
using FnNativeCall = uint64_t* (*)();
using FnGetScriptHandleBaseAddress = uint8_t* (*)(int);
using FnWorldGetAllPeds = int (*)(int*, int);

struct ShvApi {
    HMODULE module = nullptr;
    FnScriptRegister scriptRegister = nullptr;
    FnScriptUnregister scriptUnregister = nullptr;
    FnScriptWait scriptWait = nullptr;
    FnNativeInit nativeInit = nullptr;
    FnNativePush64 nativePush64 = nullptr;
    FnNativeCall nativeCall = nullptr;
    FnGetScriptHandleBaseAddress getEntityAddress = nullptr;
    FnWorldGetAllPeds worldGetAllPeds = nullptr;

    bool Bind() {
        module = GetModuleHandleA("ScriptHookV.dll");
        if (!module) {
            return false;
        }
        scriptRegister = reinterpret_cast<FnScriptRegister>(GetProcAddress(module, "?scriptRegister@@YAXPEAUHINSTANCE__@@P6AXXZ@Z"));
        if (!scriptRegister) {
            scriptRegister = reinterpret_cast<FnScriptRegister>(GetProcAddress(module, "scriptRegister"));
        }
        scriptUnregister = reinterpret_cast<FnScriptUnregister>(GetProcAddress(module, "?scriptUnregister@@YAXPEAUHINSTANCE__@@@Z"));
        if (!scriptUnregister) {
            scriptUnregister = reinterpret_cast<FnScriptUnregister>(GetProcAddress(module, "scriptUnregister"));
        }
        scriptWait = reinterpret_cast<FnScriptWait>(GetProcAddress(module, "?scriptWait@@YAXK@Z"));
        if (!scriptWait) {
            scriptWait = reinterpret_cast<FnScriptWait>(GetProcAddress(module, "scriptWait"));
        }
        nativeInit = reinterpret_cast<FnNativeInit>(GetProcAddress(module, "?nativeInit@@YAX_K@Z"));
        if (!nativeInit) {
            nativeInit = reinterpret_cast<FnNativeInit>(GetProcAddress(module, "nativeInit"));
        }
        nativePush64 = reinterpret_cast<FnNativePush64>(GetProcAddress(module, "?nativePush64@@YAX_K@Z"));
        if (!nativePush64) {
            nativePush64 = reinterpret_cast<FnNativePush64>(GetProcAddress(module, "nativePush64"));
        }
        nativeCall = reinterpret_cast<FnNativeCall>(GetProcAddress(module, "?nativeCall@@YAPEA_KXZ"));
        if (!nativeCall) {
            nativeCall = reinterpret_cast<FnNativeCall>(GetProcAddress(module, "nativeCall"));
        }
        getEntityAddress = reinterpret_cast<FnGetScriptHandleBaseAddress>(
            GetProcAddress(module, "?getScriptHandleBaseAddress@@YAPEAEH@Z"));
        if (!getEntityAddress) {
            getEntityAddress = reinterpret_cast<FnGetScriptHandleBaseAddress>(
                GetProcAddress(module, "getScriptHandleBaseAddress"));
        }
        worldGetAllPeds = reinterpret_cast<FnWorldGetAllPeds>(
            GetProcAddress(module, "?worldGetAllPeds@@YAHPEAHH@Z"));
        if (!worldGetAllPeds) {
            worldGetAllPeds = reinterpret_cast<FnWorldGetAllPeds>(
                GetProcAddress(module, "worldGetAllPeds"));
        }
        return scriptRegister && scriptWait && nativeInit && nativePush64 && nativeCall && getEntityAddress;
    }
};

ShvApi g_shv;
HMODULE g_selfModule = nullptr;
std::string g_baseDir;

uint32_t JoaatLower(const std::string& text) {
    uint32_t hash = 0;
    for (unsigned char ch : text) {
        unsigned char low = static_cast<unsigned char>(
            (ch >= 'A' && ch <= 'Z') ? (ch + ('a' - 'A')) : ch);
        hash += low;
        hash += (hash << 10);
        hash ^= (hash >> 6);
    }
    hash += (hash << 3);
    hash ^= (hash >> 11);
    hash += (hash << 15);
    return hash;
}

template <typename T>
uint64_t PackArg(T value) {
    uint64_t raw = 0;
    static_assert(sizeof(T) <= 8, "Arg too large");
    std::memcpy(&raw, &value, sizeof(T));
    return raw;
}

int CallPlayerPedId() {
    g_shv.nativeInit(kNativePlayerPedId);
    uint64_t* res = g_shv.nativeCall();
    return res ? static_cast<int>(res[0]) : 0;
}

bool CallDoesEntityExist(int entity) {
    g_shv.nativeInit(kNativeDoesEntityExist);
    g_shv.nativePush64(PackArg(entity));
    uint64_t* res = g_shv.nativeCall();
    return res && (static_cast<int>(res[0]) != 0);
}

bool CallIsEntityDead(int entity) {
    g_shv.nativeInit(kNativeIsEntityDead);
    g_shv.nativePush64(PackArg(entity));
    g_shv.nativePush64(PackArg(0));
    uint64_t* res = g_shv.nativeCall();
    return res && (static_cast<int>(res[0]) != 0);
}

uint32_t CallGetEntityModel(int entity) {
    g_shv.nativeInit(kNativeGetEntityModel);
    g_shv.nativePush64(PackArg(entity));
    uint64_t* res = g_shv.nativeCall();
    return res ? static_cast<uint32_t>(res[0]) : 0;
}

Vec3 CallGetEntityCoords(int entity) {
    g_shv.nativeInit(kNativeGetEntityCoords);
    g_shv.nativePush64(PackArg(entity));
    g_shv.nativePush64(PackArg(1));
    uint64_t* res = g_shv.nativeCall();
    if (!res) {
        return {0.0f, 0.0f, 0.0f};
    }
    ScriptVector3 sv{};
    std::memcpy(&sv, res, sizeof(sv));
    return {sv.x, sv.y, sv.z};
}

int CallGetPedBoneIndex(int ped, int boneTag) {
    g_shv.nativeInit(kNativeGetPedBoneIndex);
    g_shv.nativePush64(PackArg(ped));
    g_shv.nativePush64(PackArg(boneTag));
    uint64_t* res = g_shv.nativeCall();
    return res ? static_cast<int>(static_cast<int32_t>(res[0])) : -1;
}

int CallGetEntityBoneIndexByName(int entity, const char* boneName) {
    g_shv.nativeInit(kNativeGetEntityBoneIndexByName);
    g_shv.nativePush64(PackArg(entity));
    g_shv.nativePush64(PackArg(boneName));
    uint64_t* res = g_shv.nativeCall();
    return res ? static_cast<int>(static_cast<int32_t>(res[0])) : -1;
}

Vec3 CallGetPedBoneCoords(int ped, int boneTag) {
    g_shv.nativeInit(kNativeGetPedBoneCoords);
    g_shv.nativePush64(PackArg(ped));
    g_shv.nativePush64(PackArg(boneTag));
    g_shv.nativePush64(PackArg(0.0f));
    g_shv.nativePush64(PackArg(0.0f));
    g_shv.nativePush64(PackArg(0.0f));
    uint64_t* res = g_shv.nativeCall();
    if (!res) {
        return {0.0f, 0.0f, 0.0f};
    }
    ScriptVector3 sv{};
    std::memcpy(&sv, res, sizeof(sv));
    return {sv.x, sv.y, sv.z};
}

Vec3 VecAdd(Vec3 a, Vec3 b) { return {a.x + b.x, a.y + b.y, a.z + b.z}; }
Vec3 VecSub(Vec3 a, Vec3 b) { return {a.x - b.x, a.y - b.y, a.z - b.z}; }
Vec3 VecScale(Vec3 a, float s) { return {a.x * s, a.y * s, a.z * s}; }
float VecDot(Vec3 a, Vec3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
float VecLen(Vec3 a) { return std::sqrt(a.x * a.x + a.y * a.y + a.z * a.z); }

Vec3 VecNorm(Vec3 a) {
    float len = VecLen(a);
    if (len <= 1e-7f) {
        return {0.0f, 0.0f, 1.0f};
    }
    float inv = 1.0f / len;
    return {a.x * inv, a.y * inv, a.z * inv};
}

Vec3 ClampVecLen(Vec3 v, float maxLen) {
    float len = VecLen(v);
    if (len > maxLen && len > 1e-7f) {
        return VecScale(v, maxLen / len);
    }
    return v;
}

Vec3 QuatRotateVec(Quat q, Vec3 v) {
    float ux = q.y * v.z - q.z * v.y + q.w * v.x;
    float uy = q.z * v.x - q.x * v.z + q.w * v.y;
    float uz = q.x * v.y - q.y * v.x + q.w * v.z;
    return {
        v.x + 2.0f * (q.y * uz - q.z * uy),
        v.y + 2.0f * (q.z * ux - q.x * uz),
        v.z + 2.0f * (q.x * uy - q.y * ux),
    };
}

Quat QuatMul(Quat a, Quat b) {
    return {
        a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
        a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
        a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
        a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z,
    };
}

Quat QuatConj(Quat q) { return {-q.x, -q.y, -q.z, q.w}; }

float QuatLen(Quat q) {
    return std::sqrt(q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w);
}

Quat QuatNorm(Quat q) {
    float len = QuatLen(q);
    if (len <= 1e-8f) {
        return {0.0f, 0.0f, 0.0f, 1.0f};
    }
    float inv = 1.0f / len;
    return {q.x * inv, q.y * inv, q.z * inv, q.w * inv};
}

Quat QuatFromTwoVectors(Vec3 from, Vec3 to) {
    Vec3 a = VecNorm(from);
    Vec3 b = VecNorm(to);
    float d = VecDot(a, b);
    if (d > 1.0f) d = 1.0f;
    if (d < -1.0f) d = -1.0f;
    if (d > 0.999999f) {
        return {0.0f, 0.0f, 0.0f, 1.0f};
    }
    if (d < -0.999999f) {
        Vec3 ref = (std::fabs(a.x) < 0.9f) ? Vec3{1.0f, 0.0f, 0.0f} : Vec3{0.0f, 1.0f, 0.0f};
        Vec3 axis = VecNorm({
            a.y * ref.z - a.z * ref.y,
            a.z * ref.x - a.x * ref.z,
            a.x * ref.y - a.y * ref.x,
        });
        return {axis.x, axis.y, axis.z, 0.0f};
    }
    float cx = a.y * b.z - a.z * b.y;
    float cy = a.z * b.x - a.x * b.z;
    float cz = a.x * b.y - a.y * b.x;
    return QuatNorm({cx, cy, cz, 1.0f + d});
}

Quat Mat34ToQuat(const Mat34V& m) {
    Vec3 c0 = VecNorm({m.col0[0], m.col0[1], m.col0[2]});
    Vec3 c1 = VecNorm({m.col1[0], m.col1[1], m.col1[2]});
    Vec3 c2 = VecNorm({m.col2[0], m.col2[1], m.col2[2]});
    float m00 = c0.x, m01 = c1.x, m02 = c2.x;
    float m10 = c0.y, m11 = c1.y, m12 = c2.y;
    float m20 = c0.z, m21 = c1.z, m22 = c2.z;
    float trace = m00 + m11 + m22;
    Quat q{};
    if (trace > 0.0f) {
        float s = std::sqrt(trace + 1.0f) * 2.0f;
        q.w = 0.25f * s;
        q.x = (m21 - m12) / s;
        q.y = (m02 - m20) / s;
        q.z = (m10 - m01) / s;
    } else if (m00 > m11 && m00 > m22) {
        float s = std::sqrt(1.0f + m00 - m11 - m22) * 2.0f;
        q.w = (m21 - m12) / s;
        q.x = 0.25f * s;
        q.y = (m01 + m10) / s;
        q.z = (m02 + m20) / s;
    } else if (m11 > m22) {
        float s = std::sqrt(1.0f + m11 - m00 - m22) * 2.0f;
        q.w = (m02 - m20) / s;
        q.x = (m01 + m10) / s;
        q.y = 0.25f * s;
        q.z = (m12 + m21) / s;
    } else {
        float s = std::sqrt(1.0f + m22 - m00 - m11) * 2.0f;
        q.w = (m10 - m01) / s;
        q.x = (m02 + m20) / s;
        q.y = (m12 + m21) / s;
        q.z = 0.25f * s;
    }
    return QuatNorm(q);
}

Mat34V QuatTransToMat34(Quat q, Vec3 t) {
    Quat n = QuatNorm(q);
    float xx = n.x * n.x, yy = n.y * n.y, zz = n.z * n.z;
    float xy = n.x * n.y, xz = n.x * n.z, yz = n.y * n.z;
    float wx = n.w * n.x, wy = n.w * n.y, wz = n.w * n.z;
    Mat34V out{};
    out.col0[0] = 1.0f - 2.0f * (yy + zz);
    out.col0[1] = 2.0f * (xy + wz);
    out.col0[2] = 2.0f * (xz - wy);
    out.col0[3] = 0.0f;

    out.col1[0] = 2.0f * (xy - wz);
    out.col1[1] = 1.0f - 2.0f * (xx + zz);
    out.col1[2] = 2.0f * (yz + wx);
    out.col1[3] = 0.0f;

    out.col2[0] = 2.0f * (xz + wy);
    out.col2[1] = 2.0f * (yz - wx);
    out.col2[2] = 1.0f - 2.0f * (xx + yy);
    out.col2[3] = 0.0f;

    out.col3[0] = t.x;
    out.col3[1] = t.y;
    out.col3[2] = t.z;
    out.col3[3] = 1.0f;
    return out;
}

Vec3 TransformPoint(const Mat34V& m, Vec3 p) {
    return {
        m.col0[0] * p.x + m.col1[0] * p.y + m.col2[0] * p.z + m.col3[0],
        m.col0[1] * p.x + m.col1[1] * p.y + m.col2[1] * p.z + m.col3[1],
        m.col0[2] * p.x + m.col1[2] * p.y + m.col2[2] * p.z + m.col3[2],
    };
}

Mat34V MulMat34(const Mat34V& a, const Mat34V& b) {
    Mat34V out{};
    for (int col = 0; col < 3; ++col) {
        const float* src = (col == 0) ? b.col0 : (col == 1 ? b.col1 : b.col2);
        float* dst = (col == 0) ? out.col0 : (col == 1 ? out.col1 : out.col2);
        for (int row = 0; row < 3; ++row) {
            dst[row] = a.col0[row] * src[0] + a.col1[row] * src[1] + a.col2[row] * src[2];
        }
        dst[3] = 0.0f;
    }
    Vec3 tr = TransformPoint(a, {b.col3[0], b.col3[1], b.col3[2]});
    out.col3[0] = tr.x;
    out.col3[1] = tr.y;
    out.col3[2] = tr.z;
    out.col3[3] = 1.0f;
    return out;
}

struct BoneNodeCfg {
    std::string name;
    int tag = 0;
    int skelIndex = -1;
    float maxAngleDeg = 50.0f;
    Vec3 localPos{};
    Quat localRot{0.0f, 0.0f, 0.0f, 1.0f};
    Vec3 limitAxisLocal{0.0f, 1.0f, 0.0f};
};

struct PhysBoneChain {
    std::string name;
    int parentBoneTag = kSkelHeadTag;
    int parentSkelIndex = -1;
    int integrationType = 0;
    float pull = 0.2f;
    float spring = 0.35f;
    float stiffness = 0.2f;
    float gravity = 0.0f;
    float gravityFalloff = 0.0f;
    float immobile = 0.3f;
    int limitType = 1;
    float maxAngleX = 50.0f;
    float maxAngleZ = 45.0f;
    int isAnimated = 1;
    std::vector<BoneNodeCfg> bones;

    // Runtime Verlet state in GTA world coordinates
    bool initialized = false;
    Vec3 prevEntWorldPos{};
    Vec3 prevRootWorldPos{};
    Vec3 smoothedRootVel{};
    std::vector<Vec3> prevPosePos;
    std::vector<Vec3> worldPos;
    std::vector<Vec3> prevWorldPos;
    std::vector<float> segLengths;
};

struct BlinkBoneNode {
    std::string name;
    int tag = 0;
    int parentTag = 0;
    int skelIndex = -1;
    int parentSkelIndex = -1;
    Vec3 localPos{};
    Quat localRot{0.0f, 0.0f, 0.0f, 1.0f};
    Vec3 deltaPos{};
};

struct BlinkProfile {
    std::string model = "all";
    uint32_t modelHash = 0;
    bool enabled = true;
    float minInterval = 2.6f;
    float maxInterval = 6.0f;
    float blinkDuration = 0.215f;
    float doubleBlinkChance = 0.18f;
    float maxBlink = 1.0f;
    std::vector<BlinkBoneNode> bones;
};

struct BlinkRuntimeState {
    bool initialized = false;
    bool blinking = false;
    bool doubleBlinkPending = false;
    float waitTimer = 0.0f;
    float nextDelay = 2.2f;
    float blinkElapsed = 0.0f;
    uint32_t rngState = 0x9E3779B9U;
};

struct PluginConfig {
    bool enabled = true;
    std::string targetPedModel = "player_zero";
    uint32_t targetModelHash = 0;
    float velocityScale = 2.5f;
    float maxDeltaTime = 0.05f;
    std::vector<PhysBoneChain> chains;
    std::vector<BlinkProfile> blinkProfiles;
};

PluginConfig g_cfg;

void WriteLog(const std::string& line) {
    if (g_baseDir.empty()) return;
    std::ofstream logFile(g_baseDir + "\\GTAVPhysBones.log", std::ios::app);
    if (logFile.is_open()) {
        logFile << line << "\n";
    }
}

std::string Trim(const std::string& s) {
    size_t start = s.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) return "";
    size_t end = s.find_last_not_of(" \t\r\n");
    return s.substr(start, end - start + 1);
}

Vec3 ParseVec3(const std::string& val, Vec3 def) {
    std::stringstream ss(val);
    std::string item;
    float coords[3]{def.x, def.y, def.z};
    int idx = 0;
    while (idx < 3 && std::getline(ss, item, ',')) {
        coords[idx++] = static_cast<float>(std::atof(Trim(item).c_str()));
    }
    return {coords[0], coords[1], coords[2]};
}

Quat ParseQuat(const std::string& val) {
    std::stringstream ss(val);
    std::string item;
    float coords[4]{0.0f, 0.0f, 0.0f, 1.0f};
    int idx = 0;
    while (idx < 4 && std::getline(ss, item, ',')) {
        coords[idx++] = static_cast<float>(std::atof(Trim(item).c_str()));
    }
    return QuatNorm({coords[0], coords[1], coords[2], coords[3]});
}

bool LoadIniConfig(const std::string& iniPath, PluginConfig& outCfg) {
    std::ifstream file(iniPath);
    if (!file.is_open()) {
        return false;
    }
    outCfg = PluginConfig{};
    std::string line;
    std::string currentSection;
    int activeChainIdx = -1;
    int activeBlinkIdx = -1;

    while (std::getline(file, line)) {
        std::string trimmed = Trim(line);
        if (trimmed.empty() || trimmed[0] == ';' || trimmed[0] == '#') continue;
        if (trimmed.front() == '[' && trimmed.back() == ']') {
            currentSection = trimmed.substr(1, trimmed.size() - 2);
            if (currentSection.rfind("Chain_", 0) == 0) {
                outCfg.chains.emplace_back();
                activeChainIdx = static_cast<int>(outCfg.chains.size()) - 1;
                activeBlinkIdx = -1;
            } else if (currentSection.rfind("Blink_", 0) == 0) {
                outCfg.blinkProfiles.emplace_back();
                activeBlinkIdx = static_cast<int>(outCfg.blinkProfiles.size()) - 1;
                activeChainIdx = -1;
            } else {
                activeChainIdx = -1;
                activeBlinkIdx = -1;
            }
            continue;
        }
        size_t eqPos = trimmed.find('=');
        if (eqPos == std::string::npos) continue;
        std::string key = Trim(trimmed.substr(0, eqPos));
        std::string val = Trim(trimmed.substr(eqPos + 1));

        if (currentSection == "General") {
            if (key == "enabled") outCfg.enabled = (std::atoi(val.c_str()) != 0);
            else if (key == "target_ped_model") outCfg.targetPedModel = val;
            else if (key == "velocity_scale") outCfg.velocityScale = static_cast<float>(std::atof(val.c_str()));
            else if (key == "max_delta_time") outCfg.maxDeltaTime = static_cast<float>(std::atof(val.c_str()));
        } else if (activeChainIdx >= 0) {
            PhysBoneChain& ch = outCfg.chains[activeChainIdx];
            if (key == "name") ch.name = val;
            else if (key == "parent_bone_tag") ch.parentBoneTag = std::atoi(val.c_str());
            else if (key == "bone_count") {
                int count = std::atoi(val.c_str());
                if (count > 0 && count <= kMaxBonesPerChain) ch.bones.resize(count);
            }
            else if (key == "integration_type") ch.integrationType = std::atoi(val.c_str());
            else if (key == "pull") ch.pull = static_cast<float>(std::atof(val.c_str()));
            else if (key == "spring") ch.spring = static_cast<float>(std::atof(val.c_str()));
            else if (key == "stiffness") ch.stiffness = static_cast<float>(std::atof(val.c_str()));
            else if (key == "gravity") ch.gravity = static_cast<float>(std::atof(val.c_str()));
            else if (key == "gravity_falloff") ch.gravityFalloff = static_cast<float>(std::atof(val.c_str()));
            else if (key == "immobile") ch.immobile = static_cast<float>(std::atof(val.c_str()));
            else if (key == "limit_type") ch.limitType = std::atoi(val.c_str());
            else if (key == "max_angle_x") ch.maxAngleX = static_cast<float>(std::atof(val.c_str()));
            else if (key == "max_angle_z") ch.maxAngleZ = static_cast<float>(std::atof(val.c_str()));
            else if (key == "is_animated") ch.isAnimated = std::atoi(val.c_str());
            else if (key.rfind("bone_", 0) == 0) {
                size_t under = key.find('_', 5);
                if (under != std::string::npos) {
                    int bIdx = std::atoi(key.substr(5, under - 5).c_str());
                    std::string subKey = key.substr(under + 1);
                    if (bIdx >= 0 && bIdx < kMaxBonesPerChain) {
                        if (bIdx >= static_cast<int>(ch.bones.size())) ch.bones.resize(bIdx + 1);
                        BoneNodeCfg& bn = ch.bones[bIdx];
                        if (subKey == "name") bn.name = val;
                        else if (subKey == "tag") bn.tag = std::atoi(val.c_str());
                        else if (subKey == "max_angle") bn.maxAngleDeg = static_cast<float>(std::atof(val.c_str()));
                        else if (subKey == "local_pos") bn.localPos = ParseVec3(val, {0.0f, 0.0f, 0.0f});
                        else if (subKey == "local_rot") bn.localRot = ParseQuat(val);
                        else if (subKey == "limit_axis") bn.limitAxisLocal = VecNorm(ParseVec3(val, {0.0f, 1.0f, 0.0f}));
                    }
                }
            }
        } else if (activeBlinkIdx >= 0) {
            BlinkProfile& bp = outCfg.blinkProfiles[activeBlinkIdx];
            if (key == "model") bp.model = val;
            else if (key == "enabled") bp.enabled = (std::atoi(val.c_str()) != 0);
            else if (key == "min_interval") bp.minInterval = static_cast<float>(std::atof(val.c_str()));
            else if (key == "max_interval") bp.maxInterval = static_cast<float>(std::atof(val.c_str()));
            else if (key == "blink_duration") bp.blinkDuration = static_cast<float>(std::atof(val.c_str()));
            else if (key == "double_blink_chance") bp.doubleBlinkChance = static_cast<float>(std::atof(val.c_str()));
            else if (key == "max_blink") bp.maxBlink = static_cast<float>(std::atof(val.c_str()));
            else if (key == "bone_count") {
                int count = std::atoi(val.c_str());
                if (count > 0 && count <= kMaxBlinkBonesPerProfile) bp.bones.resize(count);
            }
            else if (key.rfind("bone_", 0) == 0) {
                size_t under = key.find('_', 5);
                if (under != std::string::npos) {
                    int bIdx = std::atoi(key.substr(5, under - 5).c_str());
                    std::string subKey = key.substr(under + 1);
                    if (bIdx >= 0 && bIdx < kMaxBlinkBonesPerProfile) {
                        if (bIdx >= static_cast<int>(bp.bones.size())) bp.bones.resize(bIdx + 1);
                        BlinkBoneNode& bn = bp.bones[bIdx];
                        if (subKey == "name") bn.name = val;
                        else if (subKey == "tag") bn.tag = std::atoi(val.c_str());
                        else if (subKey == "parent_tag") bn.parentTag = std::atoi(val.c_str());
                        else if (subKey == "local_pos") bn.localPos = ParseVec3(val, {0.0f, 0.0f, 0.0f});
                        else if (subKey == "local_rot") bn.localRot = ParseQuat(val);
                        else if (subKey == "delta_pos") bn.deltaPos = ParseVec3(val, {0.0f, 0.0f, 0.0f});
                    }
                }
            }
        }
    }

    outCfg.targetModelHash = JoaatLower(outCfg.targetPedModel);
    for (PhysBoneChain& ch : outCfg.chains) {
        size_t nodeCount = ch.bones.size();
        ch.segLengths.assign(nodeCount > 1 ? nodeCount - 1 : 0, 0.03f);
        for (size_t idx = 0; idx + 1 < nodeCount; ++idx) {
            ch.segLengths[idx] = VecLen(ch.bones[idx + 1].localPos);
        }
        ch.prevPosePos.assign(nodeCount, {0.0f, 0.0f, 0.0f});
        ch.worldPos.assign(nodeCount, {0.0f, 0.0f, 0.0f});
        ch.prevWorldPos.assign(nodeCount, {0.0f, 0.0f, 0.0f});
    }
    for (BlinkProfile& bp : outCfg.blinkProfiles) {
        bp.modelHash = (bp.model.empty() || bp.model == "all") ? 0U : JoaatLower(bp.model);
        if (bp.minInterval < 0.4f) bp.minInterval = 0.4f;
        if (bp.maxInterval < bp.minInterval) bp.maxInterval = bp.minInterval + 0.5f;
        if (bp.blinkDuration < 0.08f) bp.blinkDuration = 0.08f;
        if (bp.maxBlink < 0.0f) bp.maxBlink = 0.0f;
        if (bp.maxBlink > 1.5f) bp.maxBlink = 1.5f;
    }
    return !outCfg.chains.empty() || !outCfg.blinkProfiles.empty();
}

struct ProbeRefBone {
    int skelIndex = -1;
    Vec3 expectedLocalPos{};
};

struct ResolvedSkeleton {
    uint8_t* pedAddr = nullptr;
    uint8_t* crSkeleton = nullptr;
    uint64_t skelDataPtr = 0;
    Mat34V* parentEntityMtx = nullptr;
    Mat34V* localMatrices = nullptr;
    Mat34V* objectMatrices = nullptr;
    Mat34V* defaultTransforms = nullptr;
    uint8_t* boneDataArray = nullptr;
    int defaultTransformsOff = -1;
    int boneDataOff = -1;
    int boneDataRotOff = -1;
    int boneDataStride = 0x50;
    uint32_t numBones = 0;
    int headIndex = -1;
    int hopCount = 0;
    int off1 = -1;
    int off2 = -1;
    int off3 = -1;
};

struct SyncSnapshot {
    bool active = false;
    uint64_t crSkeleton = 0;
    uint64_t skelDataPtr = 0;
    uint64_t localMatrices = 0;
    uint64_t objectMatrices = 0;
    uint64_t defaultTransforms = 0;
    uint64_t boneDataArray = 0;
    int boneDataStride = 0x50;
    int boneDataRotOff = -1;
    uint32_t numBones = 0;
    int refIdxA = -1;
    Vec3 refPosA{};
    int count = 0;
    int boneIdx[kMaxSyncNodes]{};
    int parentBoneIdx[kMaxSyncNodes]{};
    uint8_t writeDefault[kMaxSyncNodes]{};
    Mat34V localMat[kMaxSyncNodes]{};
    Quat localQuat[kMaxSyncNodes]{};
};

struct SyncSnapshotList {
    int slotCount = 0;
    SyncSnapshot slots[kMaxTrackedPeds]{};
};

struct TrackedPedSlot {
    bool occupied = false;
    bool seenThisFrame = false;
    bool hasSkel = false;
    int pedHandle = 0;
    uint8_t* pedAddr = nullptr;
    uint32_t modelHash = 0;
    ResolvedSkeleton skel{};
    ProbeRefBone refA{};
    ProbeRefBone refB{};
    std::vector<PhysBoneChain> chains;
    std::vector<BlinkProfile> blinkProfiles;
    BlinkRuntimeState blinkState{};
    uint8_t* lastLoggedCrSkeleton = nullptr;
    uint32_t lastLoggedNumBones = 0;
    bool loggedFailure = false;
    int heavyScanCooldown = 0;
};

CRITICAL_SECTION g_syncLock;
SyncSnapshotList g_syncStateList{};
HANDLE g_syncThread = nullptr;
volatile LONG g_stopSyncThread = 0;

bool IsCanonicalUserPtr(uint64_t val) {
    return val > 0x10000ULL && val < 0x00007FFFFFFFFFFFULL && ((val & 0x7ULL) == 0);
}

bool IsReadableUserRange(uint64_t val) {
    return val > 0x10000ULL && val < 0x00007FFFFFFFFFFFULL;
}

bool SafeReadU64(uint64_t addr, uint64_t& out) {
    if (!IsReadableUserRange(addr)) return false;
    __try {
        out = *reinterpret_cast<const uint64_t*>(addr);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

bool SafeReadU16(uint64_t addr, uint16_t& out) {
    if (!IsReadableUserRange(addr)) return false;
    __try {
        out = *reinterpret_cast<const uint16_t*>(addr);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

bool SafeReadMat34(uint64_t addr, Mat34V& out) {
    if (!IsReadableUserRange(addr)) return false;
    __try {
        std::memcpy(&out, reinterpret_cast<const void*>(addr), sizeof(Mat34V));
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

bool SafeReadVec3(uint64_t addr, Vec3& out) {
    if (!IsReadableUserRange(addr)) return false;
    __try {
        const float* fp = reinterpret_cast<const float*>(addr);
        out.x = fp[0];
        out.y = fp[1];
        out.z = fp[2];
        return std::isfinite(out.x) && std::isfinite(out.y) && std::isfinite(out.z);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

bool SafeReadQuat(uint64_t addr, Quat& out) {
    if (!IsReadableUserRange(addr)) return false;
    __try {
        const float* fp = reinterpret_cast<const float*>(addr);
        out.x = fp[0];
        out.y = fp[1];
        out.z = fp[2];
        out.w = fp[3];
        return std::isfinite(out.x) && std::isfinite(out.y) &&
               std::isfinite(out.z) && std::isfinite(out.w);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

bool SafeWriteSkeletonBatch(
    ResolvedSkeleton& skel,
    const int* skelIndices,
    const Mat34V* localMatrices,
    const Mat34V* objectMatrices,
    const Quat* localQuats,
    size_t count
) {
    __try {
        for (size_t idx = 0; idx < count; ++idx) {
            int boneIdx = skelIndices[idx];
            if (boneIdx < 0 || static_cast<uint32_t>(boneIdx) >= skel.numBones) continue;
            if (skel.defaultTransforms) {
                skel.defaultTransforms[boneIdx] = localMatrices[idx];
            }
            if (skel.boneDataArray && skel.boneDataRotOff >= 0) {
                Quat* defRot = reinterpret_cast<Quat*>(
                    skel.boneDataArray + static_cast<size_t>(boneIdx) * skel.boneDataStride + skel.boneDataRotOff);
                *defRot = localQuats[idx];
            }
            skel.localMatrices[boneIdx] = localMatrices[idx];
            skel.objectMatrices[boneIdx] = objectMatrices[idx];
        }
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

bool SafeWriteLocalObjectBatch(
    ResolvedSkeleton& skel,
    const int* skelIndices,
    const Mat34V* localMatrices,
    const Mat34V* objectMatrices,
    size_t count
) {
    __try {
        for (size_t idx = 0; idx < count; ++idx) {
            int boneIdx = skelIndices[idx];
            if (boneIdx < 0 || static_cast<uint32_t>(boneIdx) >= skel.numBones) continue;
            skel.localMatrices[boneIdx] = localMatrices[idx];
            skel.objectMatrices[boneIdx] = objectMatrices[idx];
        }
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

bool SafeApplySyncSnapshot(const SyncSnapshot& snap) {
    if (!snap.active || snap.count <= 0) return false;
    __try {
        uint64_t curSkelData = *reinterpret_cast<const uint64_t*>(snap.crSkeleton + 0x00);
        uint16_t curNumBones = *reinterpret_cast<const uint16_t*>(snap.crSkeleton + 0x20);
        uint64_t curArr1 = *reinterpret_cast<const uint64_t*>(snap.crSkeleton + 0x10);
        uint64_t curArr2 = *reinterpret_cast<const uint64_t*>(snap.crSkeleton + 0x18);
        if (curSkelData != snap.skelDataPtr || curNumBones != snap.numBones) return false;
        if ((curArr1 != snap.localMatrices && curArr2 != snap.localMatrices) ||
            (curArr1 != snap.objectMatrices && curArr2 != snap.objectMatrices)) {
            return false;
        }

        Mat34V* locMats = reinterpret_cast<Mat34V*>(snap.localMatrices);
        Mat34V* objMats = reinterpret_cast<Mat34V*>(snap.objectMatrices);
        if (snap.refIdxA >= 0 && static_cast<uint32_t>(snap.refIdxA) < snap.numBones) {
            const Mat34V& refMtx = locMats[snap.refIdxA];
            float dx = refMtx.col3[0] - snap.refPosA.x;
            float dy = refMtx.col3[1] - snap.refPosA.y;
            float dz = refMtx.col3[2] - snap.refPosA.z;
            if (dx * dx + dy * dy + dz * dz > 0.01f) {
                return false;
            }
        }

        Mat34V* defMats = reinterpret_cast<Mat34V*>(snap.defaultTransforms);
        uint8_t* boneArr = reinterpret_cast<uint8_t*>(snap.boneDataArray);

        for (int idx = 0; idx < snap.count; ++idx) {
            int boneIdx = snap.boneIdx[idx];
            int parentIdx = snap.parentBoneIdx[idx];
            if (boneIdx < 0 || static_cast<uint32_t>(boneIdx) >= snap.numBones) continue;
            if (parentIdx < 0 || static_cast<uint32_t>(parentIdx) >= snap.numBones) continue;

            if (snap.writeDefault[idx]) {
                if (defMats) {
                    defMats[boneIdx] = snap.localMat[idx];
                }
                if (boneArr && snap.boneDataRotOff >= 0) {
                    Quat* defRot = reinterpret_cast<Quat*>(
                        boneArr + static_cast<size_t>(boneIdx) * snap.boneDataStride + snap.boneDataRotOff);
                    *defRot = snap.localQuat[idx];
                }
            }
            locMats[boneIdx] = snap.localMat[idx];
            objMats[boneIdx] = MulMat34(objMats[parentIdx], snap.localMat[idx]);
        }
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

DWORD WINAPI SyncThreadProc(LPVOID /*param*/) {
    static SyncSnapshotList localCopy{};
    while (InterlockedCompareExchange(&g_stopSyncThread, 0, 0) == 0) {
        EnterCriticalSection(&g_syncLock);
        localCopy = g_syncStateList;
        LeaveCriticalSection(&g_syncLock);

        for (int sIdx = 0; sIdx < localCopy.slotCount && sIdx < kMaxTrackedPeds; ++sIdx) {
            if (localCopy.slots[sIdx].active) {
                SafeApplySyncSnapshot(localCopy.slots[sIdx]);
            }
        }
        Sleep(1);
    }
    return 0;
}

void ProbeSkeletonData(
    uint64_t skelDataPtr,
    uint32_t numBones,
    const ProbeRefBone& refA,
    const ProbeRefBone& refB,
    ResolvedSkeleton& outSkel
) {
    outSkel.defaultTransforms = nullptr;
    outSkel.defaultTransformsOff = -1;
    outSkel.boneDataArray = nullptr;
    outSkel.boneDataOff = -1;
    outSkel.boneDataRotOff = -1;
    outSkel.boneDataStride = 0x50;

    if (!IsCanonicalUserPtr(skelDataPtr) || refA.skelIndex < 0 || refB.skelIndex < 0) {
        return;
    }
    if (static_cast<uint32_t>(refA.skelIndex) >= numBones ||
        static_cast<uint32_t>(refB.skelIndex) >= numBones) {
        return;
    }

    for (int off = 0x08; off <= 0x78; off += 8) {
        uint64_t ptr = 0;
        if (!SafeReadU64(skelDataPtr + off, ptr) || !IsCanonicalUserPtr(ptr)) continue;
        if (ptr == reinterpret_cast<uint64_t>(outSkel.localMatrices) ||
            ptr == reinterpret_cast<uint64_t>(outSkel.objectMatrices)) {
            continue;
        }

        // Check if ptr points to crSkeletonData::m_defaultTransforms (Mat34V[numBones], stride 0x40)
        if (!outSkel.defaultTransforms) {
            Mat34V mA{}, mB{};
            if (SafeReadMat34(ptr + static_cast<uint64_t>(refA.skelIndex) * sizeof(Mat34V), mA) &&
                SafeReadMat34(ptr + static_cast<uint64_t>(refB.skelIndex) * sizeof(Mat34V), mB)) {
                Vec3 pA{mA.col3[0], mA.col3[1], mA.col3[2]};
                Vec3 pB{mB.col3[0], mB.col3[1], mB.col3[2]};
                float c0Len = VecLen({mA.col0[0], mA.col0[1], mA.col0[2]});
                if (c0Len > 0.85f && c0Len < 1.15f &&
                    VecLen(VecSub(pA, refA.expectedLocalPos)) < 0.03f &&
                    VecLen(VecSub(pB, refB.expectedLocalPos)) < 0.03f) {
                    outSkel.defaultTransforms = reinterpret_cast<Mat34V*>(ptr);
                    outSkel.defaultTransformsOff = off;
                    continue;
                }
            }
        }

        // Check if ptr points to crBoneData[numBones] (stride 0x50)
        if (!outSkel.boneDataArray) {
            constexpr uint64_t stride = 0x50;
            uint64_t entryA = ptr + static_cast<uint64_t>(refA.skelIndex) * stride;
            uint64_t entryB = ptr + static_cast<uint64_t>(refB.skelIndex) * stride;

            Vec3 pA{}, pB{};
            Quat qA{};
            if (SafeReadVec3(entryA + 0x00, pA) && SafeReadVec3(entryB + 0x00, pB) &&
                VecLen(VecSub(pA, refA.expectedLocalPos)) < 0.03f &&
                VecLen(VecSub(pB, refB.expectedLocalPos)) < 0.03f &&
                SafeReadQuat(entryA + 0x10, qA) && std::fabs(QuatLen(qA) - 1.0f) < 0.05f) {
                outSkel.boneDataArray = reinterpret_cast<uint8_t*>(ptr);
                outSkel.boneDataOff = off;
                outSkel.boneDataRotOff = 0x10;
                outSkel.boneDataStride = static_cast<int>(stride);
                continue;
            }
            if (SafeReadVec3(entryA + 0x10, pA) && SafeReadVec3(entryB + 0x10, pB) &&
                VecLen(VecSub(pA, refA.expectedLocalPos)) < 0.03f &&
                VecLen(VecSub(pB, refB.expectedLocalPos)) < 0.03f &&
                SafeReadQuat(entryA + 0x00, qA) && std::fabs(QuatLen(qA) - 1.0f) < 0.05f) {
                outSkel.boneDataArray = reinterpret_cast<uint8_t*>(ptr);
                outSkel.boneDataOff = off;
                outSkel.boneDataRotOff = 0x00;
                outSkel.boneDataStride = static_cast<int>(stride);
                continue;
            }
        }
    }
}

bool IsValidMat34(const Mat34V& m) {
    if (!std::isfinite(m.col0[0]) || !std::isfinite(m.col0[1]) || !std::isfinite(m.col0[2]) ||
        !std::isfinite(m.col1[0]) || !std::isfinite(m.col1[1]) || !std::isfinite(m.col1[2]) ||
        !std::isfinite(m.col2[0]) || !std::isfinite(m.col2[1]) || !std::isfinite(m.col2[2]) ||
        !std::isfinite(m.col3[0]) || !std::isfinite(m.col3[1]) || !std::isfinite(m.col3[2])) {
        return false;
    }
    float len0 = VecLen({m.col0[0], m.col0[1], m.col0[2]});
    float len1 = VecLen({m.col1[0], m.col1[1], m.col1[2]});
    float len2 = VecLen({m.col2[0], m.col2[1], m.col2[2]});
    return len0 > 0.7f && len0 < 1.3f &&
           len1 > 0.7f && len1 < 1.3f &&
           len2 > 0.7f && len2 < 1.3f;
}

bool ValidateMatPairLayout(
    uint64_t localCandPtr,
    uint64_t objCandPtr,
    uint32_t numBones,
    const Mat34V& entMtx,
    const Vec3& entOrigin,
    int headIdx,
    const ProbeRefBone& refA,
    const ProbeRefBone& refB,
    const Vec3& expectedEntityPos,
    const Vec3& expectedHeadWorldPos
) {
    if (refA.skelIndex >= 0 && refB.skelIndex >= 0 &&
        static_cast<uint32_t>(refA.skelIndex) < numBones &&
        static_cast<uint32_t>(refB.skelIndex) < numBones) {
        Mat34V mA{}, mB{};
        if (SafeReadMat34(localCandPtr + static_cast<uint64_t>(refA.skelIndex) * sizeof(Mat34V), mA) &&
            SafeReadMat34(localCandPtr + static_cast<uint64_t>(refB.skelIndex) * sizeof(Mat34V), mB)) {
            Vec3 pA{mA.col3[0], mA.col3[1], mA.col3[2]};
            Vec3 pB{mB.col3[0], mB.col3[1], mB.col3[2]};
            if (IsValidMat34(mA) && IsValidMat34(mB) &&
                VecLen(VecSub(pA, refA.expectedLocalPos)) < 0.03f &&
                VecLen(VecSub(pB, refB.expectedLocalPos)) < 0.03f) {
                Mat34V headObj{};
                if (SafeReadMat34(objCandPtr + static_cast<uint64_t>(headIdx) * sizeof(Mat34V), headObj) &&
                    IsValidMat34(headObj)) {
                    Vec3 headLocalObj{headObj.col3[0], headObj.col3[1], headObj.col3[2]};
                    if (VecLen(headLocalObj) < 5.0f) {
                        return true;
                    }
                }
            }
        }
        return false;
    }

    if (VecLen(VecSub(entOrigin, expectedEntityPos)) < 2.0f) {
        Mat34V headObj{};
        if (SafeReadMat34(objCandPtr + static_cast<uint64_t>(headIdx) * sizeof(Mat34V), headObj) &&
            IsValidMat34(headObj)) {
            Vec3 headWorld = TransformPoint(entMtx, {headObj.col3[0], headObj.col3[1], headObj.col3[2]});
            if (VecLen(VecSub(headWorld, expectedHeadWorldPos)) < 0.75f) {
                return true;
            }
        }
    }
    return false;
}

bool ValidateCandidateCrSkeleton(
    uint64_t pedBase,
    uint64_t candSkel,
    int headIdx,
    const ProbeRefBone& refA,
    const ProbeRefBone& refB,
    const Vec3& expectedEntityPos,
    const Vec3& expectedHeadWorldPos,
    ResolvedSkeleton& outSkel
) {
    if (!IsCanonicalUserPtr(candSkel)) return false;

    uint16_t numBones16 = 0;
    if (!SafeReadU16(candSkel + 0x20, numBones16)) return false;

    int maxReq = headIdx;
    if (refA.skelIndex > maxReq) maxReq = refA.skelIndex;
    if (refB.skelIndex > maxReq) maxReq = refB.skelIndex;
    if (numBones16 < static_cast<uint16_t>(maxReq + 1) || numBones16 > 1024) {
        return false;
    }

    uint64_t skelDataPtr = 0;
    uint64_t parentMtxPtr = 0;
    uint64_t arr1Ptr = 0;
    uint64_t arr2Ptr = 0;
    if (!SafeReadU64(candSkel + 0x00, skelDataPtr) ||
        !SafeReadU64(candSkel + 0x08, parentMtxPtr) ||
        !SafeReadU64(candSkel + 0x10, arr1Ptr) ||
        !SafeReadU64(candSkel + 0x18, arr2Ptr)) {
        return false;
    }
    if (!IsCanonicalUserPtr(skelDataPtr) ||
        !IsCanonicalUserPtr(arr1Ptr) || !IsCanonicalUserPtr(arr2Ptr) ||
        arr1Ptr == arr2Ptr) {
        return false;
    }

    Mat34V entMtx{};
    bool gotEntMtx = false;
    if (IsCanonicalUserPtr(parentMtxPtr) && SafeReadMat34(parentMtxPtr, entMtx) && IsValidMat34(entMtx)) {
        gotEntMtx = true;
    } else {
        uint64_t fallbackMtxPtr = pedBase + 0x60;
        if (SafeReadMat34(fallbackMtxPtr, entMtx) && IsValidMat34(entMtx)) {
            parentMtxPtr = fallbackMtxPtr;
            gotEntMtx = true;
        }
    }
    if (!gotEntMtx) {
        return false;
    }

    Vec3 entOrigin{entMtx.col3[0], entMtx.col3[1], entMtx.col3[2]};
    if ((refA.skelIndex < 0 || refB.skelIndex < 0) &&
        VecLen(VecSub(entOrigin, expectedEntityPos)) > 2.0f) {
        return false;
    }

    uint32_t numBones = numBones16;
    if (ValidateMatPairLayout(arr1Ptr, arr2Ptr, numBones, entMtx, entOrigin, headIdx, refA, refB, expectedEntityPos, expectedHeadWorldPos)) {
        outSkel.crSkeleton = reinterpret_cast<uint8_t*>(candSkel);
        outSkel.skelDataPtr = skelDataPtr;
        outSkel.parentEntityMtx = reinterpret_cast<Mat34V*>(parentMtxPtr);
        outSkel.localMatrices = reinterpret_cast<Mat34V*>(arr1Ptr);
        outSkel.objectMatrices = reinterpret_cast<Mat34V*>(arr2Ptr);
        outSkel.numBones = numBones;
        outSkel.headIndex = headIdx;
        ProbeSkeletonData(skelDataPtr, numBones, refA, refB, outSkel);
        return true;
    }

    if (ValidateMatPairLayout(arr2Ptr, arr1Ptr, numBones, entMtx, entOrigin, headIdx, refA, refB, expectedEntityPos, expectedHeadWorldPos)) {
        outSkel.crSkeleton = reinterpret_cast<uint8_t*>(candSkel);
        outSkel.skelDataPtr = skelDataPtr;
        outSkel.parentEntityMtx = reinterpret_cast<Mat34V*>(parentMtxPtr);
        outSkel.localMatrices = reinterpret_cast<Mat34V*>(arr2Ptr);
        outSkel.objectMatrices = reinterpret_cast<Mat34V*>(arr1Ptr);
        outSkel.numBones = numBones;
        outSkel.headIndex = headIdx;
        ProbeSkeletonData(skelDataPtr, numBones, refA, refB, outSkel);
        return true;
    }
    return false;
}

void DumpPedPointerDiagnostics(uint8_t* pedAddr, const Vec3& entPos, const Vec3& headPos, const ProbeRefBone& refA, const ProbeRefBone& refB) {
    uint64_t base = reinterpret_cast<uint64_t>(pedAddr);
    std::ostringstream oss;
    oss << "[DIAG] ped=0x" << std::hex << base << std::dec
        << " ent=(" << entPos.x << "," << entPos.y << "," << entPos.z << ")"
        << " head=(" << headPos.x << "," << headPos.y << "," << headPos.z << ")"
        << " refA=" << refA.skelIndex << " refB=" << refB.skelIndex;
    WriteLog(oss.str());

    std::ostringstream ptrLine;
    ptrLine << "[DIAG] ped+0x20..0x80:";
    for (int off = 0x20; off <= 0x80; off += 8) {
        uint64_t val = 0;
        if (SafeReadU64(base + off, val)) {
            ptrLine << " +0x" << std::hex << off << "=0x" << val;
        }
    }
    WriteLog(ptrLine.str());

    uint64_t p30 = 0;
    if (SafeReadU64(base + 0x30, p30) && IsCanonicalUserPtr(p30)) {
        std::ostringstream p30Line;
        p30Line << "[DIAG] p30(0x" << std::hex << p30 << ")+0x00..0x80:";
        for (int off = 0x00; off <= 0x80; off += 8) {
            uint64_t val = 0;
            if (SafeReadU64(p30 + off, val)) {
                p30Line << " +0x" << off << "=0x" << val;
            }
        }
        WriteLog(p30Line.str());
    }
}

bool FollowResolvedHopPath(uint64_t pedBase, const ResolvedSkeleton& skel, uint64_t& outCrSkel) {
    outCrSkel = 0;
    if (!IsCanonicalUserPtr(pedBase) || skel.hopCount < 1 || skel.hopCount > 3 || skel.off1 < 0) {
        return false;
    }
    uint64_t ptr = 0;
    if (!SafeReadU64(pedBase + static_cast<uint64_t>(skel.off1), ptr) || !IsCanonicalUserPtr(ptr)) {
        return false;
    }
    if (skel.hopCount == 1) {
        outCrSkel = ptr;
        return true;
    }
    if (skel.off2 < 0 || !SafeReadU64(ptr + static_cast<uint64_t>(skel.off2), ptr) || !IsCanonicalUserPtr(ptr)) {
        return false;
    }
    if (skel.hopCount == 2) {
        outCrSkel = ptr;
        return true;
    }
    if (skel.off3 < 0 || !SafeReadU64(ptr + static_cast<uint64_t>(skel.off3), ptr) || !IsCanonicalUserPtr(ptr)) {
        return false;
    }
    outCrSkel = ptr;
    return true;
}

bool GetLiveEntityMatrix(uint64_t pedBase, ResolvedSkeleton& skel, Mat34V& outEntMtx) {
    uint64_t crSkel = reinterpret_cast<uint64_t>(skel.crSkeleton);
    uint64_t parentMtxPtr = 0;
    if (SafeReadU64(crSkel + 0x08, parentMtxPtr) && IsCanonicalUserPtr(parentMtxPtr) &&
        SafeReadMat34(parentMtxPtr, outEntMtx) && IsValidMat34(outEntMtx)) {
        skel.parentEntityMtx = reinterpret_cast<Mat34V*>(parentMtxPtr);
        return true;
    }
    uint64_t fallbackPtr = pedBase + 0x60;
    if (SafeReadMat34(fallbackPtr, outEntMtx) && IsValidMat34(outEntMtx)) {
        skel.parentEntityMtx = reinterpret_cast<Mat34V*>(fallbackPtr);
        return true;
    }
    return false;
}

bool IsResolvedSkeletonStillValid(
    int ped,
    uint8_t* pedAddr,
    ResolvedSkeleton& skel,
    const ProbeRefBone& refA,
    const ProbeRefBone& refB
) {
    if (!skel.crSkeleton || !skel.localMatrices || !skel.objectMatrices) return false;
    if (skel.pedAddr != pedAddr) return false;

    uint64_t pedBase = reinterpret_cast<uint64_t>(pedAddr);
    uint64_t liveCrSkel = 0;
    if (!FollowResolvedHopPath(pedBase, skel, liveCrSkel) ||
        liveCrSkel != reinterpret_cast<uint64_t>(skel.crSkeleton)) {
        return false;
    }

    uint64_t curSkelData = 0;
    uint64_t curArr1 = 0;
    uint64_t curArr2 = 0;
    uint16_t curNumBones = 0;
    if (!SafeReadU64(liveCrSkel + 0x00, curSkelData) ||
        !SafeReadU64(liveCrSkel + 0x10, curArr1) ||
        !SafeReadU64(liveCrSkel + 0x18, curArr2) ||
        !SafeReadU16(liveCrSkel + 0x20, curNumBones)) {
        return false;
    }

    uint64_t cachedLoc = reinterpret_cast<uint64_t>(skel.localMatrices);
    uint64_t cachedObj = reinterpret_cast<uint64_t>(skel.objectMatrices);
    if (curSkelData != skel.skelDataPtr || curNumBones != skel.numBones) {
        return false;
    }
    if ((curArr1 != cachedLoc && curArr2 != cachedLoc) ||
        (curArr1 != cachedObj && curArr2 != cachedObj)) {
        return false;
    }

    if (CallGetPedBoneIndex(ped, kSkelHeadTag) != skel.headIndex) {
        return false;
    }

    if (skel.defaultTransforms && skel.defaultTransformsOff >= 0) {
        uint64_t curDefTransforms = 0;
        if (!SafeReadU64(curSkelData + static_cast<uint64_t>(skel.defaultTransformsOff), curDefTransforms) ||
            curDefTransforms != reinterpret_cast<uint64_t>(skel.defaultTransforms)) {
            return false;
        }
    }
    if (skel.boneDataArray && skel.boneDataOff >= 0) {
        uint64_t curBoneData = 0;
        if (!SafeReadU64(curSkelData + static_cast<uint64_t>(skel.boneDataOff), curBoneData) ||
            curBoneData != reinterpret_cast<uint64_t>(skel.boneDataArray)) {
            return false;
        }
    }

    if (skel.headIndex >= 0 && static_cast<uint32_t>(skel.headIndex) < curNumBones) {
        Mat34V entMtx{};
        Mat34V headObj{};
        if (!GetLiveEntityMatrix(pedBase, skel, entMtx) ||
            !SafeReadMat34(cachedObj + static_cast<uint64_t>(skel.headIndex) * sizeof(Mat34V), headObj) ||
            !IsValidMat34(headObj)) {
            return false;
        }
        if (VecLen({headObj.col3[0], headObj.col3[1], headObj.col3[2]}) >= 5.0f) {
            return false;
        }
    }

    if (refA.skelIndex >= 0 && static_cast<uint32_t>(refA.skelIndex) < curNumBones) {
        Mat34V mA{};
        if (!SafeReadMat34(cachedLoc + static_cast<uint64_t>(refA.skelIndex) * sizeof(Mat34V), mA) ||
            !IsValidMat34(mA)) {
            return false;
        }
        Vec3 pA{mA.col3[0], mA.col3[1], mA.col3[2]};
        if (VecLen(VecSub(pA, refA.expectedLocalPos)) > 0.05f) {
            return false;
        }
    }
    if (refB.skelIndex >= 0 && static_cast<uint32_t>(refB.skelIndex) < curNumBones) {
        Mat34V mB{};
        if (!SafeReadMat34(cachedLoc + static_cast<uint64_t>(refB.skelIndex) * sizeof(Mat34V), mB) ||
            !IsValidMat34(mB)) {
            return false;
        }
        Vec3 pB{mB.col3[0], mB.col3[1], mB.col3[2]};
        if (VecLen(VecSub(pB, refB.expectedLocalPos)) > 0.05f) {
            return false;
        }
    }
    return true;
}

bool TryResolveCandidate(
    uint64_t pedBase,
    uint64_t candSkel,
    int headIdx,
    const ProbeRefBone& refA,
    const ProbeRefBone& refB,
    const Vec3& entPos,
    const Vec3& headPos,
    int hopCount,
    int off1,
    int off2,
    int off3,
    ResolvedSkeleton& outSkel
) {
    if (!ValidateCandidateCrSkeleton(pedBase, candSkel, headIdx, refA, refB, entPos, headPos, outSkel)) {
        return false;
    }
    outSkel.pedAddr = reinterpret_cast<uint8_t*>(pedBase);
    outSkel.hopCount = hopCount;
    outSkel.off1 = off1;
    outSkel.off2 = off2;
    outSkel.off3 = off3;
    return true;
}

bool TryResolvePedSkeleton(
    int ped,
    int headIdx,
    const ProbeRefBone& refA,
    const ProbeRefBone& refB,
    bool allowHeavyScan,
    ResolvedSkeleton& outSkel
) {
    uint8_t* pedAddr = g_shv.getEntityAddress(ped);
    uint64_t base = reinterpret_cast<uint64_t>(pedAddr);
    if (!IsCanonicalUserPtr(base) || headIdx < 0) return false;

    Vec3 entPos = CallGetEntityCoords(ped);
    Vec3 headPos = CallGetPedBoneCoords(ped, kSkelHeadTag);

    // 0. Fast-path known GTA V CPed -> ped+0x50 -> +0x30 -> +0x20 crSkeleton chain
    uint64_t p50 = 0;
    if (SafeReadU64(base + 0x50, p50) && IsCanonicalUserPtr(p50)) {
        uint64_t p50_30 = 0;
        if (SafeReadU64(p50 + 0x30, p50_30) && IsCanonicalUserPtr(p50_30)) {
            uint64_t cand20 = 0;
            if (SafeReadU64(p50_30 + 0x20, cand20) &&
                TryResolveCandidate(base, cand20, headIdx, refA, refB, entPos, headPos, 3, 0x50, 0x30, 0x20, outSkel)) {
                return true;
            }
            for (int skelOff = 0x10; skelOff <= 0x40; skelOff += 8) {
                if (skelOff == 0x20) continue;
                uint64_t cand = 0;
                if (SafeReadU64(p50_30 + skelOff, cand) &&
                    TryResolveCandidate(base, cand, headIdx, refA, refB, entPos, headPos, 3, 0x50, 0x30, skelOff, outSkel)) {
                    return true;
                }
            }
        }
    }

    // 1. Check standard RAGE path: ped+0x30 (fragInst) -> +0x68 (fragCacheEntry) -> +0x100..0x220
    uint64_t fragInst = 0;
    if (SafeReadU64(base + 0x30, fragInst) && IsCanonicalUserPtr(fragInst)) {
        uint64_t midPtr = 0;
        if (SafeReadU64(fragInst + 0x68, midPtr) && IsCanonicalUserPtr(midPtr)) {
            for (int skelOff = 0x100; skelOff <= 0x220; skelOff += 8) {
                uint64_t cand = 0;
                if (SafeReadU64(midPtr + skelOff, cand) &&
                    TryResolveCandidate(base, cand, headIdx, refA, refB, entPos, headPos, 3, 0x30, 0x68, skelOff, outSkel)) {
                    return true;
                }
            }
        }
    }

    if (!allowHeavyScan) {
        return false;
    }

    // 2. 1-hop scan across pedAddr + 0x08..0x300
    for (int off1 = 0x08; off1 <= 0x300; off1 += 8) {
        uint64_t p1 = 0;
        if (!SafeReadU64(base + off1, p1) || !IsCanonicalUserPtr(p1)) continue;
        if (TryResolveCandidate(base, p1, headIdx, refA, refB, entPos, headPos, 1, off1, -1, -1, outSkel)) {
            return true;
        }
    }

    // 3. 2-hop scan across pedAddr + 0x08..0x300 -> +0x00..0x280
    for (int off1 = 0x08; off1 <= 0x300; off1 += 8) {
        uint64_t p1 = 0;
        if (!SafeReadU64(base + off1, p1) || !IsCanonicalUserPtr(p1)) continue;
        for (int off2 = 0x00; off2 <= 0x280; off2 += 8) {
            uint64_t p2 = 0;
            if (!SafeReadU64(p1 + off2, p2) || !IsCanonicalUserPtr(p2)) continue;
            if (TryResolveCandidate(base, p2, headIdx, refA, refB, entPos, headPos, 2, off1, off2, -1, outSkel)) {
                return true;
            }
        }
    }

    // 4. 3-hop scan across entity component slots (off1 0x08..0x180 -> off2 0x00..0x100 -> off3 0x00..0x280)
    for (int off1 = 0x08; off1 <= 0x180; off1 += 8) {
        uint64_t p1 = 0;
        if (!SafeReadU64(base + off1, p1) || !IsCanonicalUserPtr(p1)) continue;
        for (int off2 = 0x00; off2 <= 0x100; off2 += 8) {
            uint64_t p2 = 0;
            if (!SafeReadU64(p1 + off2, p2) || !IsCanonicalUserPtr(p2)) continue;
            for (int off3 = 0x00; off3 <= 0x280; off3 += 8) {
                uint64_t p3 = 0;
                if (!SafeReadU64(p2 + off3, p3) || !IsCanonicalUserPtr(p3)) continue;
                if (TryResolveCandidate(base, p3, headIdx, refA, refB, entPos, headPos, 3, off1, off2, off3, outSkel)) {
                    return true;
                }
            }
        }
    }

    return false;
}

void ComputeChainMatrices(
    PhysBoneChain& chain,
    const Mat34V& entityWorldMtx,
    const Mat34V& parentObjMtx,
    float deltaTime,
    Mat34V* outLocalMatrices,
    Mat34V* outObjectMatrices,
    Quat* outLocalQuats,
    size_t& outCount
) {
    outCount = 0;
    const size_t n = chain.bones.size();
    if (n < 2 || n > kMaxBonesPerChain) return;

    const Vec3 entWorldPos{entityWorldMtx.col3[0], entityWorldMtx.col3[1], entityWorldMtx.col3[2]};
    const Mat34V parentWorldMtx = MulMat34(entityWorldMtx, parentObjMtx);
    const Vec3 parentWorldPos{parentWorldMtx.col3[0], parentWorldMtx.col3[1], parentWorldMtx.col3[2]};
    const Quat parentWorldRot = Mat34ToQuat(parentWorldMtx);

    Vec3 posePos[kMaxBonesPerChain]{};
    Vec3 curPos = parentWorldPos;
    Quat curRot = parentWorldRot;
    for (size_t idx = 0; idx < n; ++idx) {
        curPos = VecAdd(curPos, QuatRotateVec(curRot, chain.bones[idx].localPos));
        curRot = QuatNorm(QuatMul(curRot, chain.bones[idx].localRot));
        posePos[idx] = curPos;
    }

    Vec3 rootStepDelta = VecSub(posePos[0], chain.prevRootWorldPos);
    Vec3 prevRelRoot = VecSub(chain.prevRootWorldPos, chain.prevEntWorldPos);
    Vec3 curRelRoot = VecSub(posePos[0], entWorldPos);
    Vec3 relRootDelta = VecSub(curRelRoot, prevRelRoot);
    if (!chain.initialized || VecLen(rootStepDelta) > 12.0f || VecLen(relRootDelta) > 0.85f) {
        chain.worldPos.assign(posePos, posePos + n);
        chain.prevWorldPos.assign(posePos, posePos + n);
        chain.prevPosePos.assign(posePos, posePos + n);
        chain.prevEntWorldPos = entWorldPos;
        chain.prevRootWorldPos = posePos[0];
        chain.smoothedRootVel = {0.0f, 0.0f, 0.0f};
        chain.initialized = true;
    } else {
        float clampedDt = (deltaTime < 1e-4f) ? 1e-4f : (deltaTime > g_cfg.maxDeltaTime ? g_cfg.maxDeltaTime : deltaTime);
        float invDt = 1.0f / clampedDt;
        Vec3 instRootVel = VecScale(rootStepDelta, invDt);

        // Separate steady locomotion/fall velocity (~0.18s EMA) from clamped step-bob / turn impulses
        float emaAlpha = clampedDt / 0.18f;
        if (emaAlpha > 1.0f) emaAlpha = 1.0f;
        chain.smoothedRootVel = VecAdd(
            VecScale(chain.smoothedRootVel, 1.0f - emaAlpha),
            VecScale(instRootVel, emaAlpha));
        Vec3 steadyShift = VecScale(chain.smoothedRootVel, clampedDt);
        Vec3 oscRootDelta = ClampVecLen(VecSub(rootStepDelta, steadyShift), 0.06f);
        chain.prevEntWorldPos = entWorldPos;
        chain.prevRootWorldPos = posePos[0];

        float immobileScale = (chain.immobile < 0.0f) ? 0.0f : (chain.immobile > 1.0f ? 1.0f : chain.immobile);
        Vec3 immobileShift = VecAdd(steadyShift, VecScale(oscRootDelta, immobileScale));

        float rateScale = clampedDt * 60.0f;
        float springClamped = (chain.spring < 0.0f) ? 0.0f : (chain.spring > 1.0f ? 1.0f : chain.spring);
        float velBase = 0.88f + 0.05f * springClamped; // underdamped VRChat-style [0.88..0.93]
        float velRetention = std::pow(velBase, rateScale);

        float pullCompl = 1.0f - chain.pull;
        if (pullCompl < 0.0f) pullCompl = 0.0f;
        if (pullCompl > 1.0f) pullCompl = 1.0f;
        float pullFactor = 1.0f - std::pow(pullCompl, rateScale);

        float impulseGain = (g_cfg.velocityScale > 1.0f) ? (g_cfg.velocityScale - 1.0f) : 0.0f;

        chain.worldPos[0] = posePos[0];
        chain.prevWorldPos[0] = posePos[0];
        chain.prevPosePos[0] = posePos[0];

        // Stage 1: Sub-damped Verlet prediction + steady-locomotion shift + head-bob impulse
        float gravFalloffClamped = (chain.gravityFalloff < 0.0f) ? 0.0f : (chain.gravityFalloff > 1.0f ? 1.0f : chain.gravityFalloff);
        float effGravity = chain.gravity * (1.0f - gravFalloffClamped);
        for (size_t idx = 1; idx < n; ++idx) {
            Vec3 nodeOscDelta = ClampVecLen(VecSub(VecSub(posePos[idx], chain.prevPosePos[idx]), steadyShift), 0.06f);
            chain.prevPosePos[idx] = posePos[idx];

            Vec3 shiftedPrev = VecAdd(chain.prevWorldPos[idx], immobileShift);
            Vec3 shiftedCurr = VecAdd(chain.worldPos[idx], immobileShift);
            Vec3 vel = VecScale(VecSub(shiftedCurr, shiftedPrev), velRetention);
            Vec3 oscKick = VecScale(nodeOscDelta, -impulseGain * (1.0f - immobileScale));
            Vec3 grav{0.0f, 0.0f, -9.81f * effGravity * clampedDt * clampedDt};

            chain.prevWorldPos[idx] = shiftedCurr;
            Vec3 pred = VecAdd(VecAdd(VecAdd(shiftedCurr, vel), oscKick), grav);
            Vec3 pullDelta = VecScale(VecSub(posePos[idx], pred), pullFactor);
            chain.worldPos[idx] = VecAdd(pred, pullDelta);
        }
    }

    // Stage 2: Angle cone limit constraints + segment length clamp
    Quat worldRotOut[kMaxBonesPerChain]{};
    for (size_t idx = 0; idx + 1 < n; ++idx) {
        Vec3 nodePos = chain.worldPos[idx];
        Vec3 childPos = chain.worldPos[idx + 1];
        Vec3 curDir = VecNorm(VecSub(childPos, nodePos));

        Quat expParentRot = (idx == 0) ? parentWorldRot : worldRotOut[idx - 1];
        Quat restNodeRot = QuatNorm(QuatMul(expParentRot, chain.bones[idx].localRot));
        Vec3 restSegDir = VecNorm(QuatRotateVec(restNodeRot, chain.bones[idx + 1].localPos));

        if (chain.limitType > 0) {
            Vec3 limRef = VecNorm(QuatRotateVec(restNodeRot, chain.bones[idx].limitAxisLocal));
            float cosAng = VecDot(curDir, limRef);
            if (cosAng > 1.0f) cosAng = 1.0f;
            if (cosAng < -1.0f) cosAng = -1.0f;
            float curAng = std::acos(cosAng);
            float maxAng = chain.bones[idx].maxAngleDeg * (kPi / 180.0f);
            if (curAng > maxAng && maxAng >= 0.0f) {
                Vec3 tang = VecSub(curDir, VecScale(limRef, cosAng));
                if (VecLen(tang) > 1e-6f) {
                    Vec3 tangUnit = VecNorm(tang);
                    curDir = VecNorm(VecAdd(
                        VecScale(limRef, std::cos(maxAng)),
                        VecScale(tangUnit, std::sin(maxAng))));
                }
            }
        }

        chain.worldPos[idx + 1] = VecAdd(nodePos, VecScale(curDir, chain.segLengths[idx]));
        Quat aimDelta = QuatFromTwoVectors(restSegDir, curDir);
        worldRotOut[idx] = QuatNorm(QuatMul(aimDelta, restNodeRot));
    }
    worldRotOut[n - 1] = QuatNorm(QuatMul(worldRotOut[n - 2], chain.bones[n - 1].localRot));

    const Quat entWorldRotInv = QuatConj(Mat34ToQuat(entityWorldMtx));

    for (size_t idx = 0; idx < n; ++idx) {
        Quat pWorldRot = (idx == 0) ? parentWorldRot : worldRotOut[idx - 1];
        Quat locRot = QuatNorm(QuatMul(QuatConj(pWorldRot), worldRotOut[idx]));
        outLocalQuats[idx] = locRot;
        outLocalMatrices[idx] = QuatTransToMat34(locRot, chain.bones[idx].localPos);

        Vec3 objPos = QuatRotateVec(entWorldRotInv, VecSub(chain.worldPos[idx], entWorldPos));
        Quat objRot = QuatNorm(QuatMul(entWorldRotInv, worldRotOut[idx]));
        outObjectMatrices[idx] = QuatTransToMat34(objRot, objPos);
    }
    outCount = n;
}

float NextBlinkRand01(BlinkRuntimeState& st) {
    uint32_t s = st.rngState ? st.rngState : 0x9E3779B9U;
    s ^= s << 13;
    s ^= s >> 17;
    s ^= s << 5;
    st.rngState = s;
    return static_cast<float>(s & 0x00FFFFFFU) / static_cast<float>(0x01000000U);
}

float EvaluateNaturalBlinkCurve(float elapsed, float duration) {
    if (duration <= 0.01f) return 0.0f;
    float u = elapsed / duration;
    if (u <= 0.0f || u >= 1.0f) return 0.0f;
    constexpr float kCloseEnd = 0.28f;
    constexpr float kHoldEnd = 0.40f;
    if (u < kCloseEnd) {
        float c = u / kCloseEnd;
        return c * c * (3.0f - 2.0f * c);
    }
    if (u < kHoldEnd) {
        return 1.0f;
    }
    float s = (u - kHoldEnd) / (1.0f - kHoldEnd);
    float e = s * (2.0f - s);
    float amt = 1.0f - (e * e * (3.0f - 2.0f * e));
    return (amt < 0.0f) ? 0.0f : ((amt > 1.0f) ? 1.0f : amt);
}

const BlinkProfile* FindMatchingBlinkProfile(
    const std::vector<BlinkProfile>& profiles,
    uint32_t modelHash
) {
    const BlinkProfile* fallback = nullptr;
    for (const BlinkProfile& bp : profiles) {
        if (!bp.enabled || bp.bones.empty()) continue;
        if (bp.modelHash != 0U && bp.modelHash == modelHash) {
            return &bp;
        }
        if ((bp.model.empty() || bp.model == "all") && !fallback) {
            fallback = &bp;
        }
    }
    return fallback;
}

float UpdatePedBlinkAmount(TrackedPedSlot& slot, const BlinkProfile& bp, float deltaTime) {
    BlinkRuntimeState& st = slot.blinkState;
    if (!st.initialized) {
        uint64_t ptrVal = reinterpret_cast<uintptr_t>(slot.pedAddr);
        st.rngState = static_cast<uint32_t>((ptrVal >> 3) ^ slot.modelHash ^ 0xA5A55A5AU);
        if (st.rngState == 0U) st.rngState = 0x9E3779B9U;
        st.nextDelay = 0.5f + NextBlinkRand01(st) * 2.5f;
        st.waitTimer = 0.0f;
        st.blinking = false;
        st.doubleBlinkPending = false;
        st.blinkElapsed = 0.0f;
        st.initialized = true;
    }

    if (CallIsEntityDead(slot.pedHandle)) {
        st.blinking = false;
        st.doubleBlinkPending = false;
        st.blinkElapsed = 0.0f;
        return 0.0f;
    }

    float blinkDt = (deltaTime < 0.0f) ? 0.0f : ((deltaTime > g_cfg.maxDeltaTime) ? g_cfg.maxDeltaTime : deltaTime);
    if (st.blinking) {
        st.blinkElapsed += blinkDt;
        if (st.blinkElapsed >= bp.blinkDuration) {
            st.blinking = false;
            st.blinkElapsed = 0.0f;
            st.waitTimer = 0.0f;
            if (!st.doubleBlinkPending && NextBlinkRand01(st) < bp.doubleBlinkChance) {
                st.doubleBlinkPending = true;
                st.nextDelay = 0.11f + NextBlinkRand01(st) * 0.06f;
            } else {
                st.doubleBlinkPending = false;
                float uMix = 0.5f * (NextBlinkRand01(st) + NextBlinkRand01(st));
                st.nextDelay = bp.minInterval + uMix * (bp.maxInterval - bp.minInterval);
            }
            return 0.0f;
        }
        return EvaluateNaturalBlinkCurve(st.blinkElapsed, bp.blinkDuration) * bp.maxBlink;
    }

    st.waitTimer += blinkDt;
    if (st.waitTimer >= st.nextDelay) {
        st.blinking = true;
        st.blinkElapsed = 0.0f;
        st.waitTimer = 0.0f;
    }
    return 0.0f;
}

void UpdatePedChainsAndBuildSync(
    TrackedPedSlot& slot,
    const Mat34V& entityWorldMtx,
    float deltaTime,
    SyncSnapshot& outSnap
) {
    outSnap = SyncSnapshot{};
    outSnap.crSkeleton = reinterpret_cast<uint64_t>(slot.skel.crSkeleton);
    outSnap.skelDataPtr = slot.skel.skelDataPtr;
    outSnap.localMatrices = reinterpret_cast<uint64_t>(slot.skel.localMatrices);
    outSnap.objectMatrices = reinterpret_cast<uint64_t>(slot.skel.objectMatrices);
    outSnap.defaultTransforms = reinterpret_cast<uint64_t>(slot.skel.defaultTransforms);
    outSnap.boneDataArray = reinterpret_cast<uint64_t>(slot.skel.boneDataArray);
    outSnap.boneDataStride = slot.skel.boneDataStride;
    outSnap.boneDataRotOff = slot.skel.boneDataRotOff;
    outSnap.numBones = slot.skel.numBones;
    outSnap.refIdxA = slot.refA.skelIndex;
    outSnap.refPosA = slot.refA.expectedLocalPos;

    for (auto& ch : slot.chains) {
        if (ch.bones.size() < 2 || ch.bones.size() > static_cast<size_t>(kMaxBonesPerChain)) continue;
        bool allBonesValid = true;
        for (const auto& bn : ch.bones) {
            if (bn.skelIndex < 0 || static_cast<uint32_t>(bn.skelIndex) >= slot.skel.numBones) {
                allBonesValid = false;
                break;
            }
        }
        if (!allBonesValid) continue;

        Mat34V parentObjMtx{};
        if (ch.parentSkelIndex < 0 || static_cast<uint32_t>(ch.parentSkelIndex) >= slot.skel.numBones) continue;
        if (!SafeReadMat34(
                reinterpret_cast<uint64_t>(slot.skel.objectMatrices) +
                    static_cast<uint64_t>(ch.parentSkelIndex) * sizeof(Mat34V),
                parentObjMtx) ||
            !IsValidMat34(parentObjMtx)) {
            continue;
        }

        Mat34V localMats[kMaxBonesPerChain]{};
        Mat34V objMats[kMaxBonesPerChain]{};
        Quat localQuats[kMaxBonesPerChain]{};
        size_t outCount = 0;
        ComputeChainMatrices(ch, entityWorldMtx, parentObjMtx, deltaTime, localMats, objMats, localQuats, outCount);
        if (outCount == 0) continue;

        bool finiteMatrices = true;
        for (size_t idx = 0; idx < outCount; ++idx) {
            if (!IsValidMat34(localMats[idx]) || !IsValidMat34(objMats[idx])) {
                finiteMatrices = false;
                break;
            }
        }
        if (!finiteMatrices) {
            ch.initialized = false;
            continue;
        }

        int indices[kMaxBonesPerChain]{};
        for (size_t idx = 0; idx < outCount; ++idx) {
            indices[idx] = ch.bones[idx].skelIndex;
        }
        SafeWriteSkeletonBatch(slot.skel, indices, localMats, objMats, localQuats, outCount);

        for (size_t idx = 0; idx < outCount && outSnap.count < kMaxSyncNodes; ++idx) {
            int bIdx = ch.bones[idx].skelIndex;
            int pIdx = (idx == 0) ? ch.parentSkelIndex : ch.bones[idx - 1].skelIndex;
            if (bIdx < 0 || pIdx < 0) continue;
            outSnap.boneIdx[outSnap.count] = bIdx;
            outSnap.parentBoneIdx[outSnap.count] = pIdx;
            outSnap.writeDefault[outSnap.count] = 1;
            outSnap.localMat[outSnap.count] = localMats[idx];
            outSnap.localQuat[outSnap.count] = localQuats[idx];
            outSnap.count++;
        }
    }

    const BlinkProfile* activeBlink = FindMatchingBlinkProfile(slot.blinkProfiles, slot.modelHash);
    if (activeBlink != nullptr) {
        float blinkAmt = UpdatePedBlinkAmount(slot, *activeBlink, deltaTime);
        Mat34V blinkLocalMats[kMaxBlinkBonesPerProfile]{};
        Mat34V blinkObjMats[kMaxBlinkBonesPerProfile]{};
        int blinkIndices[kMaxBlinkBonesPerProfile]{};
        int blinkParents[kMaxBlinkBonesPerProfile]{};
        Quat blinkQuats[kMaxBlinkBonesPerProfile]{};
        size_t blinkValid = 0;

        for (size_t idx = 0;
             idx < activeBlink->bones.size() && idx < static_cast<size_t>(kMaxBlinkBonesPerProfile);
             ++idx) {
            const BlinkBoneNode& bn = activeBlink->bones[idx];
            if (bn.skelIndex < 0 || static_cast<uint32_t>(bn.skelIndex) >= slot.skel.numBones) continue;
            if (bn.parentSkelIndex < 0 || static_cast<uint32_t>(bn.parentSkelIndex) >= slot.skel.numBones) continue;

            Mat34V parentObjMtx{};
            bool foundPrev = false;
            for (size_t prev = 0; prev < blinkValid; ++prev) {
                if (blinkIndices[prev] == bn.parentSkelIndex) {
                    parentObjMtx = blinkObjMats[prev];
                    foundPrev = true;
                    break;
                }
            }
            if (!foundPrev) {
                if (!SafeReadMat34(
                        reinterpret_cast<uint64_t>(slot.skel.objectMatrices) +
                            static_cast<uint64_t>(bn.parentSkelIndex) * sizeof(Mat34V),
                        parentObjMtx) ||
                    !IsValidMat34(parentObjMtx)) {
                    continue;
                }
            }

            Vec3 animatedPos = VecAdd(bn.localPos, VecScale(bn.deltaPos, blinkAmt));
            Mat34V locMat = QuatTransToMat34(bn.localRot, animatedPos);
            Mat34V objMat = MulMat34(parentObjMtx, locMat);
            if (!IsValidMat34(locMat) || !IsValidMat34(objMat)) continue;

            blinkIndices[blinkValid] = bn.skelIndex;
            blinkParents[blinkValid] = bn.parentSkelIndex;
            blinkLocalMats[blinkValid] = locMat;
            blinkObjMats[blinkValid] = objMat;
            blinkQuats[blinkValid] = bn.localRot;
            blinkValid++;
        }

        if (blinkValid > 0) {
            SafeWriteLocalObjectBatch(slot.skel, blinkIndices, blinkLocalMats, blinkObjMats, blinkValid);
            for (size_t idx = 0; idx < blinkValid && outSnap.count < kMaxSyncNodes; ++idx) {
                outSnap.boneIdx[outSnap.count] = blinkIndices[idx];
                outSnap.parentBoneIdx[outSnap.count] = blinkParents[idx];
                outSnap.writeDefault[outSnap.count] = 0;
                outSnap.localMat[outSnap.count] = blinkLocalMats[idx];
                outSnap.localQuat[outSnap.count] = blinkQuats[idx];
                outSnap.count++;
            }
        }
    }

    outSnap.active = (outSnap.count > 0);
}

void PublishSyncSnapshotList(const SyncSnapshotList& nextList) {
    EnterCriticalSection(&g_syncLock);
    g_syncStateList = nextList;
    LeaveCriticalSection(&g_syncLock);
}

void ClearSyncSnapshot() {
    EnterCriticalSection(&g_syncLock);
    g_syncStateList.slotCount = 0;
    LeaveCriticalSection(&g_syncLock);
}

bool ResolveChainBoneIndices(
    int ped,
    std::vector<PhysBoneChain>& chains,
    std::vector<BlinkProfile>& blinkProfiles,
    ProbeRefBone& outRefA,
    ProbeRefBone& outRefB
) {
    bool changed = false;
    ProbeRefBone nextRefA{};
    ProbeRefBone nextRefB{};
    std::vector<ProbeRefBone> rootRefs;
    std::vector<ProbeRefBone> allResolvedRefs;

    for (size_t cIdx = 0; cIdx < chains.size(); ++cIdx) {
        PhysBoneChain& ch = chains[cIdx];
        int nextParent = CallGetPedBoneIndex(ped, ch.parentBoneTag);
        if (nextParent != ch.parentSkelIndex) {
            changed = true;
            ch.parentSkelIndex = nextParent;
        }
        for (size_t bIdx = 0; bIdx < ch.bones.size(); ++bIdx) {
            BoneNodeCfg& bn = ch.bones[bIdx];
            int resolved = CallGetPedBoneIndex(ped, bn.tag);
            if (resolved < 0 && !bn.name.empty()) {
                resolved = CallGetEntityBoneIndexByName(ped, bn.name.c_str());
            }
            if (resolved != bn.skelIndex) {
                changed = true;
                bn.skelIndex = resolved;
            }
            if (resolved >= 0) {
                ProbeRefBone candidate{resolved, bn.localPos};
                if (bIdx == 0) {
                    rootRefs.push_back(candidate);
                }
                allResolvedRefs.push_back(candidate);
            }
        }
    }

    for (BlinkProfile& bp : blinkProfiles) {
        for (BlinkBoneNode& bn : bp.bones) {
            int resolved = CallGetPedBoneIndex(ped, bn.tag);
            if (resolved < 0 && !bn.name.empty()) {
                resolved = CallGetEntityBoneIndexByName(ped, bn.name.c_str());
            }
            int resolvedParent = CallGetPedBoneIndex(ped, bn.parentTag);
            if (resolved != bn.skelIndex || resolvedParent != bn.parentSkelIndex) {
                changed = true;
                bn.skelIndex = resolved;
                bn.parentSkelIndex = resolvedParent;
            }
        }
    }

    const std::vector<ProbeRefBone>& refSource = (rootRefs.size() >= 2) ? rootRefs : allResolvedRefs;
    if (!refSource.empty()) {
        nextRefA = refSource[0];
        for (size_t i = 1; i < refSource.size(); ++i) {
            if (refSource[i].skelIndex != nextRefA.skelIndex) {
                nextRefB = refSource[i];
                break;
            }
        }
    }
    if (outRefA.skelIndex != nextRefA.skelIndex || outRefB.skelIndex != nextRefB.skelIndex) {
        changed = true;
    }
    outRefA = nextRefA;
    outRefB = nextRefB;
    return changed;
}

void LogBoneIndexChange(const TrackedPedSlot& slot) {
    std::ostringstream oss;
    oss << "[INFO] Bone indices changed ped=0x"
        << std::hex << reinterpret_cast<uintptr_t>(slot.pedAddr)
        << " model=0x" << slot.modelHash << std::dec;
    int activeCount = 0;
    for (const auto& ch : slot.chains) {
        if (ch.parentSkelIndex < 0 || ch.bones.empty() || ch.bones[0].skelIndex < 0) continue;
        ++activeCount;
        oss << " | " << ch.name << " parent=" << ch.parentSkelIndex << " nodes=[";
        for (size_t i = 0; i < ch.bones.size(); ++i) {
            if (i > 0) oss << ",";
            oss << ch.bones[i].skelIndex;
        }
        oss << "]";
    }
    oss << " (active=" << activeCount << "/" << slot.chains.size() << ")";
    WriteLog(oss.str());
}

bool HasCustomChainBones(int ped, uint32_t pedModelHash, bool& outHasHead) {
    outHasHead = false;
    if (g_cfg.chains.empty() && g_cfg.blinkProfiles.empty()) return false;
    if (CallGetPedBoneIndex(ped, kSkelHeadTag) < 0) return false;
    outHasHead = true;
    for (const auto& ch : g_cfg.chains) {
        if (ch.bones.empty()) continue;
        int rootTag = ch.bones[0].tag;
        if (rootTag != 0) {
            if (CallGetPedBoneIndex(ped, rootTag) >= 0) {
                return true;
            }
        } else if (!ch.bones[0].name.empty()) {
            if (CallGetEntityBoneIndexByName(ped, ch.bones[0].name.c_str()) >= 0) {
                return true;
            }
        }
    }
    const BlinkProfile* bp = FindMatchingBlinkProfile(g_cfg.blinkProfiles, pedModelHash);
    if (bp != nullptr && (bp->modelHash == pedModelHash || bp->model == "all")) {
        const BlinkBoneNode& bn = bp->bones[0];
        if (bn.tag != 0 && CallGetPedBoneIndex(ped, bn.tag) >= 0) {
            return true;
        }
    }
    return false;
}

bool IsEligiblePhysBonePed(int ped, bool bypassNegCache, int scanTick, uint32_t& outModelHash) {
    static std::unordered_map<uint32_t, int> s_negModelCooldownTick;
    outModelHash = CallGetEntityModel(ped);
    if (!bypassNegCache && outModelHash != 0) {
        auto it = s_negModelCooldownTick.find(outModelHash);
        if (it != s_negModelCooldownTick.end() && scanTick < it->second) {
            return false;
        }
    }
    bool hasHead = false;
    bool eligible = HasCustomChainBones(ped, outModelHash, hasHead);
    if (outModelHash != 0) {
        if (eligible) {
            s_negModelCooldownTick.erase(outModelHash);
        } else if (hasHead) {
            if (s_negModelCooldownTick.size() > 512) {
                s_negModelCooldownTick.clear();
            }
            s_negModelCooldownTick[outModelHash] = scanTick + 180;
        }
    }
    return eligible;
}

int CollectCandidatePeds(
    int* outHandles,
    uint8_t** outAddrs,
    uint32_t* outModels,
    int maxOut
) {
    static int s_scanTick = 0;
    ++s_scanTick;
    int count = 0;
    auto tryAdd = [&](int ped, bool bypassNegCache) {
        if (count >= maxOut || ped == 0 || !CallDoesEntityExist(ped)) return;
        uint8_t* addr = g_shv.getEntityAddress(ped);
        if (!IsCanonicalUserPtr(reinterpret_cast<uint64_t>(addr))) return;
        for (int i = 0; i < count; ++i) {
            if (outAddrs[i] == addr) return;
        }
        uint32_t modelHash = 0;
        if (!IsEligiblePhysBonePed(ped, bypassNegCache, s_scanTick, modelHash)) return;
        outHandles[count] = ped;
        outAddrs[count] = addr;
        outModels[count] = modelHash;
        count++;
    };

    tryAdd(CallPlayerPedId(), true);

    if (g_shv.worldGetAllPeds && count < maxOut) {
        int worldPeds[kMaxWorldPedsScan]{};
        int found = g_shv.worldGetAllPeds(worldPeds, kMaxWorldPedsScan);
        for (int i = 0; i < found && count < maxOut; ++i) {
            tryAdd(worldPeds[i], false);
        }
    }
    return count;
}

void LogSkeletonResolution(const TrackedPedSlot& slot, bool isReResolve) {
    std::ostringstream oss;
    oss << (isReResolve ? "[INFO] Re-resolved ped=0x" : "[INFO] Resolved ped=0x")
        << std::hex << reinterpret_cast<uintptr_t>(slot.pedAddr)
        << " model=0x" << slot.modelHash
        << " crSkeleton=0x" << reinterpret_cast<uintptr_t>(slot.skel.crSkeleton)
        << " skelData=0x" << slot.skel.skelDataPtr
        << " hop=" << std::dec << slot.skel.hopCount
        << " off=(0x" << std::hex << slot.skel.off1
        << ",0x" << slot.skel.off2
        << ",0x" << slot.skel.off3 << ")"
        << " defTransOff=0x" << slot.skel.defaultTransformsOff
        << " boneDataOff=0x" << slot.skel.boneDataOff
        << " boneDataRotOff=0x" << slot.skel.boneDataRotOff
        << std::dec << " numBones=" << slot.skel.numBones
        << " headIdx=" << slot.skel.headIndex;
    int activeCount = 0;
    for (const auto& ch : slot.chains) {
        if (ch.parentSkelIndex < 0 || ch.bones.empty() || ch.bones[0].skelIndex < 0) continue;
        ++activeCount;
        oss << " | " << ch.name << " parent=" << ch.parentSkelIndex << " nodes=[";
        for (size_t i = 0; i < ch.bones.size(); ++i) {
            if (i > 0) oss << ",";
            oss << ch.bones[i].skelIndex;
        }
        oss << "]";
    }
    oss << " (active=" << activeCount << "/" << slot.chains.size() << ")";
    WriteLog(oss.str());
}

void ScriptMain() {
    std::string iniPath = g_baseDir + "\\GTAVPhysBones.ini";
    if (!LoadIniConfig(iniPath, g_cfg) || !g_cfg.enabled) {
        WriteLog("[WARN] GTAVPhysBones.ini missing or disabled at: " + iniPath);
        return;
    }

    {
        std::ostringstream initOss;
        initOss << "[INIT] GTAVPhysBones loaded ini=" << iniPath
                << " target=" << g_cfg.targetPedModel
                << " hash=0x" << std::hex << g_cfg.targetModelHash
                << std::dec << " chains=" << g_cfg.chains.size()
                << " velScale=" << g_cfg.velocityScale
                << " worldScan=" << (g_shv.worldGetAllPeds ? 1 : 0);
        WriteLog(initOss.str());
    }

    std::vector<TrackedPedSlot> slots(kMaxTrackedPeds);

    LARGE_INTEGER freq{}, lastTime{}, curTime{};
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&lastTime);

    while (true) {
        g_shv.scriptWait(0);
        QueryPerformanceCounter(&curTime);
        float dt = static_cast<float>(curTime.QuadPart - lastTime.QuadPart) / static_cast<float>(freq.QuadPart);
        lastTime = curTime;
        bool resetAllChains = false;
        if (dt <= 0.0f || dt > 0.25f) {
            resetAllChains = true;
            dt = 1.0f / 60.0f;
        }

        int candHandles[kMaxTrackedPeds]{};
        uint8_t* candAddrs[kMaxTrackedPeds]{};
        uint32_t candModels[kMaxTrackedPeds]{};
        int candCount = CollectCandidatePeds(candHandles, candAddrs, candModels, kMaxTrackedPeds);
        if (candCount == 0) {
            ClearSyncSnapshot();
            for (auto& slot : slots) {
                slot = TrackedPedSlot{};
            }
            continue;
        }

        for (auto& slot : slots) {
            slot.seenThisFrame = false;
        }

        int matchedSlotIdx[kMaxTrackedPeds]{};
        for (int c = 0; c < candCount; ++c) {
            matchedSlotIdx[c] = -1;
            for (int s = 0; s < kMaxTrackedPeds; ++s) {
                if (slots[s].occupied && slots[s].pedAddr == candAddrs[c]) {
                    slots[s].pedHandle = candHandles[c];
                    slots[s].modelHash = candModels[c];
                    slots[s].seenThisFrame = true;
                    if (resetAllChains) {
                        for (auto& ch : slots[s].chains) ch.initialized = false;
                    }
                    matchedSlotIdx[c] = s;
                    break;
                }
            }
        }

        for (int c = 0; c < candCount; ++c) {
            if (matchedSlotIdx[c] >= 0) continue;
            int targetIdx = -1;
            for (int s = 0; s < kMaxTrackedPeds; ++s) {
                if (!slots[s].occupied) {
                    targetIdx = s;
                    break;
                }
            }
            if (targetIdx < 0) {
                for (int s = 0; s < kMaxTrackedPeds; ++s) {
                    if (!slots[s].seenThisFrame) {
                        targetIdx = s;
                        break;
                    }
                }
            }
            if (targetIdx < 0) continue;

            TrackedPedSlot& slot = slots[targetIdx];
            slot = TrackedPedSlot{};
            slot.occupied = true;
            slot.seenThisFrame = true;
            slot.pedHandle = candHandles[c];
            slot.pedAddr = candAddrs[c];
            slot.modelHash = candModels[c];
            slot.chains = g_cfg.chains;
            slot.blinkProfiles = g_cfg.blinkProfiles;
            matchedSlotIdx[c] = targetIdx;
        }

        for (int s = 0; s < kMaxTrackedPeds; ++s) {
            if (slots[s].occupied && !slots[s].seenThisFrame) {
                slots[s] = TrackedPedSlot{};
            }
        }

        static SyncSnapshotList nextSyncList{};
        nextSyncList.slotCount = 0;
        for (int i = 0; i < kMaxTrackedPeds; ++i) {
            nextSyncList.slots[i].active = false;
            nextSyncList.slots[i].count = 0;
        }
        for (int s = 0; s < kMaxTrackedPeds; ++s) {
            TrackedPedSlot& slot = slots[s];
            if (!slot.occupied || !slot.seenThisFrame) continue;

            if (slot.hasSkel) {
                if (ResolveChainBoneIndices(slot.pedHandle, slot.chains, slot.blinkProfiles, slot.refA, slot.refB)) {
                    LogBoneIndexChange(slot);
                    slot.hasSkel = false;
                    slot.skel = ResolvedSkeleton{};
                    slot.heavyScanCooldown = 0;
                    for (auto& ch : slot.chains) ch.initialized = false;
                } else if (!IsResolvedSkeletonStillValid(slot.pedHandle, slot.pedAddr, slot.skel, slot.refA, slot.refB)) {
                    slot.hasSkel = false;
                    slot.skel = ResolvedSkeleton{};
                    slot.heavyScanCooldown = 0;
                    for (auto& ch : slot.chains) ch.initialized = false;
                }
            }

            if (!slot.hasSkel) {
                int headIdx = CallGetPedBoneIndex(slot.pedHandle, kSkelHeadTag);
                ResolveChainBoneIndices(slot.pedHandle, slot.chains, slot.blinkProfiles, slot.refA, slot.refB);
                bool allowHeavy = (slot.heavyScanCooldown <= 0);
                if (!TryResolvePedSkeleton(slot.pedHandle, headIdx, slot.refA, slot.refB, allowHeavy, slot.skel)) {
                    if (allowHeavy) {
                        slot.heavyScanCooldown = kRescanCooldownFrames;
                        if (!slot.loggedFailure) {
                            std::ostringstream errOss;
                            errOss << "[WARN] Failed to resolve crSkeleton for ped=0x" << std::hex
                                   << reinterpret_cast<uintptr_t>(slot.pedAddr)
                                   << " model=0x" << slot.modelHash
                                   << std::dec << " headIdx=" << headIdx;
                            WriteLog(errOss.str());
                            DumpPedPointerDiagnostics(
                                slot.pedAddr,
                                CallGetEntityCoords(slot.pedHandle),
                                CallGetPedBoneCoords(slot.pedHandle, kSkelHeadTag),
                                slot.refA,
                                slot.refB);
                            slot.loggedFailure = true;
                        }
                    } else {
                        --slot.heavyScanCooldown;
                    }
                    continue;
                }

                slot.hasSkel = true;
                slot.heavyScanCooldown = 0;
                slot.loggedFailure = false;
                for (auto& ch : slot.chains) ch.initialized = false;

                bool isReResolve = (slot.lastLoggedCrSkeleton != nullptr);
                LogSkeletonResolution(slot, isReResolve);
                slot.lastLoggedCrSkeleton = slot.skel.crSkeleton;
                slot.lastLoggedNumBones = slot.skel.numBones;
            }

            Mat34V entMtx{};
            if (!GetLiveEntityMatrix(reinterpret_cast<uint64_t>(slot.pedAddr), slot.skel, entMtx)) {
                slot.hasSkel = false;
                slot.skel = ResolvedSkeleton{};
                continue;
            }

            if (nextSyncList.slotCount < kMaxTrackedPeds) {
                SyncSnapshot& outSnap = nextSyncList.slots[nextSyncList.slotCount];
                UpdatePedChainsAndBuildSync(slot, entMtx, dt, outSnap);
                if (outSnap.active) {
                    nextSyncList.slotCount++;
                }
            }
        }

        PublishSyncSnapshotList(nextSyncList);
    }
}

} // namespace

BOOL APIENTRY DllMain(HMODULE hInstance, DWORD reason, LPVOID /*reserved*/) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hInstance);
        g_selfModule = hInstance;
        char pathBuf[MAX_PATH]{};
        GetModuleFileNameA(hInstance, pathBuf, MAX_PATH);
        std::string fullPath(pathBuf);
        size_t slash = fullPath.find_last_of("\\/");
        g_baseDir = (slash != std::string::npos) ? fullPath.substr(0, slash) : ".";

        InitializeCriticalSection(&g_syncLock);
        g_stopSyncThread = 0;
        g_syncThread = CreateThread(nullptr, 0, SyncThreadProc, nullptr, 0, nullptr);

        if (g_shv.Bind()) {
            g_shv.scriptRegister(hInstance, ScriptMain);
        }
    } else if (reason == DLL_PROCESS_DETACH) {
        InterlockedExchange(&g_stopSyncThread, 1);
        if (g_syncThread) {
            WaitForSingleObject(g_syncThread, 500);
            CloseHandle(g_syncThread);
            g_syncThread = nullptr;
        }
        DeleteCriticalSection(&g_syncLock);
        if (g_shv.scriptUnregister) {
            g_shv.scriptUnregister(hInstance);
        }
    }
    return TRUE;
}
