#pragma once
/*
 * gtav_physbones_math.hpp
 * =======================
 * Layer 1 (Foundation): Constants, ScriptHookV dynamic API binding, native
 * hash wrappers, and 3D vector/quaternion/matrix algebra primitives.
 *
 * All functions live inside `namespace gtav_physbones` with zero 1- or
 * 2-character identifiers so both human readers and automated static audits
 * have unambiguous names across every mathematical operation.
 */

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>

namespace gtav_physbones {

// ---------------------------------------------------------------------------
// Engine & Solver Limits
// ---------------------------------------------------------------------------
constexpr float kPi = 3.14159265358979323846f;
constexpr int kMaxBonesPerChain = 16;
constexpr int kMaxSyncNodes = 256;
constexpr int kMaxTrackedPeds = 32;
constexpr int kMaxWorldPedsScan = 256;
constexpr int kRescanCooldownFrames = 30;
constexpr int kSkelHeadTag = 31086;
constexpr int kMaxBlinkBonesPerProfile = 8;

// ---------------------------------------------------------------------------
// ScriptHookV Native Hashes (verified present in GTA V Legacy ScriptHookV.dll)
// ---------------------------------------------------------------------------
constexpr uint64_t kNativePlayerPedId = 0xD80958FC74E988A6ULL;
constexpr uint64_t kNativeGetEntityModel = 0x9F47B058362C84B5ULL;
constexpr uint64_t kNativeGetEntityCoords = 0x3FEF770D40960D5AULL;
constexpr uint64_t kNativeDoesEntityExist = 0x7239B21A38F536BAULL;
constexpr uint64_t kNativeIsEntityDead = 0x5F9532F3B5CC2551ULL;
constexpr uint64_t kNativeGetPedBoneIndex = 0x3F428D08BE5AAE31ULL;
constexpr uint64_t kNativeGetPedBoneCoords = 0x17C07FC640E86B4EULL;
constexpr uint64_t kNativeGetEntityBoneIndexByName = 0xFB71170B7E76ACBAULL;
constexpr uint64_t kNativeGetWorldPositionOfEntityBone = 0x44A8FCB8ED227738ULL;

// ---------------------------------------------------------------------------
// Core Math & RAGE Matrix Types
// ---------------------------------------------------------------------------
/** 3D Cartesian vector / point in meters (RAGE / GTA V world or bone space). */
struct Vec3 {
    float coord_x;
    float coord_y;
    float coord_z;
};

/** Unit quaternion representing 3D orientation `(x, y, z, w)`. */
struct Quat {
    float quat_x;
    float quat_y;
    float quat_z;
    float quat_w;
};

/** 16-byte aligned 3x4 column-major affine matrix matching `rage::Mat34V`. */
struct alignas(16) Mat34V {
    float col0[4];
    float col1[4];
    float col2[4];
    float col3[4];
};

/** ScriptHookV native vector return slot (each float lane padded to 8 bytes). */
struct ScriptVector3 {
    float coord_x;
    uint32_t pad0;
    float coord_y;
    uint32_t pad1;
    float coord_z;
    uint32_t pad2;
};

// ---------------------------------------------------------------------------
// ScriptHookV Dynamic Export Binding
// ---------------------------------------------------------------------------
using FnScriptRegister = void (*)(HMODULE, void (*)());
using FnScriptUnregister = void (*)(HMODULE);
using FnScriptWait = void (*)(DWORD);
using FnNativeInit = void (*)(uint64_t);
using FnNativePush64 = void (*)(uint64_t);
using FnNativeCall = uint64_t* (*)();
using FnGetScriptHandleBaseAddress = uint8_t* (*)(int);
using FnWorldGetAllPeds = int (*)(int*, int);

/** Late-bound table of ScriptHookV exported entry points. */
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

    /** Resolve ScriptHookV.dll function pointers (mangled C++ and unmangled fallbacks). */
    bool Bind() {
        module = GetModuleHandleA("ScriptHookV.dll");
        if (!module) {
            return false;
        }
        scriptRegister = reinterpret_cast<FnScriptRegister>(
            GetProcAddress(module, "?scriptRegister@@YAXPEAUHINSTANCE__@@P6AXXZ@Z"));
        if (!scriptRegister) {
            scriptRegister = reinterpret_cast<FnScriptRegister>(
                GetProcAddress(module, "scriptRegister"));
        }
        scriptUnregister = reinterpret_cast<FnScriptUnregister>(
            GetProcAddress(module, "?scriptUnregister@@YAXPEAUHINSTANCE__@@@Z"));
        if (!scriptUnregister) {
            scriptUnregister = reinterpret_cast<FnScriptUnregister>(
                GetProcAddress(module, "scriptUnregister"));
        }
        scriptWait = reinterpret_cast<FnScriptWait>(
            GetProcAddress(module, "?scriptWait@@YAXK@Z"));
        if (!scriptWait) {
            scriptWait = reinterpret_cast<FnScriptWait>(GetProcAddress(module, "scriptWait"));
        }
        nativeInit = reinterpret_cast<FnNativeInit>(
            GetProcAddress(module, "?nativeInit@@YAX_K@Z"));
        if (!nativeInit) {
            nativeInit = reinterpret_cast<FnNativeInit>(GetProcAddress(module, "nativeInit"));
        }
        nativePush64 = reinterpret_cast<FnNativePush64>(
            GetProcAddress(module, "?nativePush64@@YAX_K@Z"));
        if (!nativePush64) {
            nativePush64 = reinterpret_cast<FnNativePush64>(
                GetProcAddress(module, "nativePush64"));
        }
        nativeCall = reinterpret_cast<FnNativeCall>(
            GetProcAddress(module, "?nativeCall@@YAPEA_KXZ"));
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
        return scriptRegister && scriptWait && nativeInit && nativePush64 && nativeCall &&
               getEntityAddress;
    }
};

inline ShvApi g_shv{};
inline HMODULE g_selfModule = nullptr;
inline std::string g_baseDir{};

// ---------------------------------------------------------------------------
// Hashing & Native Invocation Helpers
// ---------------------------------------------------------------------------
/** Compute case-folded GTA V JOAAT hash for model names (matching RAGE strings). */
inline uint32_t JoaatLower(const std::string& text) {
    uint32_t hash = 0;
    for (unsigned char char_code : text) {
        unsigned char low_char = static_cast<unsigned char>(
            (char_code >= 'A' && char_code <= 'Z') ? (char_code + ('a' - 'A')) : char_code);
        hash += low_char;
        hash += (hash << 10);
        hash ^= (hash >> 6);
    }
    hash += (hash << 3);
    hash ^= (hash >> 11);
    hash += (hash << 15);
    return hash;
}

template <typename ArgType>
inline uint64_t PackArg(ArgType value) {
    uint64_t raw = 0;
    static_assert(sizeof(ArgType) <= 8, "Arg too large");
    std::memcpy(&raw, &value, sizeof(ArgType));
    return raw;
}

inline int CallPlayerPedId() {
    g_shv.nativeInit(kNativePlayerPedId);
    uint64_t* result_ptr = g_shv.nativeCall();
    return result_ptr ? static_cast<int>(result_ptr[0]) : 0;
}

inline bool CallDoesEntityExist(int entity) {
    g_shv.nativeInit(kNativeDoesEntityExist);
    g_shv.nativePush64(PackArg(entity));
    uint64_t* result_ptr = g_shv.nativeCall();
    return result_ptr && (static_cast<int>(result_ptr[0]) != 0);
}

inline bool CallIsEntityDead(int entity) {
    g_shv.nativeInit(kNativeIsEntityDead);
    g_shv.nativePush64(PackArg(entity));
    g_shv.nativePush64(PackArg(0));
    uint64_t* result_ptr = g_shv.nativeCall();
    return result_ptr && (static_cast<int>(result_ptr[0]) != 0);
}

inline uint32_t CallGetEntityModel(int entity) {
    g_shv.nativeInit(kNativeGetEntityModel);
    g_shv.nativePush64(PackArg(entity));
    uint64_t* result_ptr = g_shv.nativeCall();
    return result_ptr ? static_cast<uint32_t>(result_ptr[0]) : 0;
}

inline Vec3 CallGetEntityCoords(int entity) {
    g_shv.nativeInit(kNativeGetEntityCoords);
    g_shv.nativePush64(PackArg(entity));
    g_shv.nativePush64(PackArg(1));
    uint64_t* result_ptr = g_shv.nativeCall();
    if (!result_ptr) {
        return {0.0f, 0.0f, 0.0f};
    }
    ScriptVector3 script_vec{};
    std::memcpy(&script_vec, result_ptr, sizeof(script_vec));
    return {script_vec.coord_x, script_vec.coord_y, script_vec.coord_z};
}

inline int CallGetPedBoneIndex(int ped, int boneTag) {
    g_shv.nativeInit(kNativeGetPedBoneIndex);
    g_shv.nativePush64(PackArg(ped));
    g_shv.nativePush64(PackArg(boneTag));
    uint64_t* result_ptr = g_shv.nativeCall();
    return result_ptr ? static_cast<int>(static_cast<int32_t>(result_ptr[0])) : -1;
}

inline int CallGetEntityBoneIndexByName(int entity, const char* boneName) {
    g_shv.nativeInit(kNativeGetEntityBoneIndexByName);
    g_shv.nativePush64(PackArg(entity));
    g_shv.nativePush64(PackArg(boneName));
    uint64_t* result_ptr = g_shv.nativeCall();
    return result_ptr ? static_cast<int>(static_cast<int32_t>(result_ptr[0])) : -1;
}

inline Vec3 CallGetPedBoneCoords(int ped, int boneTag) {
    g_shv.nativeInit(kNativeGetPedBoneCoords);
    g_shv.nativePush64(PackArg(ped));
    g_shv.nativePush64(PackArg(boneTag));
    g_shv.nativePush64(PackArg(0.0f));
    g_shv.nativePush64(PackArg(0.0f));
    g_shv.nativePush64(PackArg(0.0f));
    uint64_t* result_ptr = g_shv.nativeCall();
    if (!result_ptr) {
        return {0.0f, 0.0f, 0.0f};
    }
    ScriptVector3 script_vec{};
    std::memcpy(&script_vec, result_ptr, sizeof(script_vec));
    return {script_vec.coord_x, script_vec.coord_y, script_vec.coord_z};
}

// ---------------------------------------------------------------------------
// 3D Vector, Quaternion & Matrix Algebra
// ---------------------------------------------------------------------------
inline Vec3 VecAdd(Vec3 lhs_vec, Vec3 rhs_vec) {
    return {
        lhs_vec.coord_x + rhs_vec.coord_x,
        lhs_vec.coord_y + rhs_vec.coord_y,
        lhs_vec.coord_z + rhs_vec.coord_z,
    };
}

inline Vec3 VecSub(Vec3 lhs_vec, Vec3 rhs_vec) {
    return {
        lhs_vec.coord_x - rhs_vec.coord_x,
        lhs_vec.coord_y - rhs_vec.coord_y,
        lhs_vec.coord_z - rhs_vec.coord_z,
    };
}

inline Vec3 VecScale(Vec3 vec_in, float scale_val) {
    return {
        vec_in.coord_x * scale_val,
        vec_in.coord_y * scale_val,
        vec_in.coord_z * scale_val,
    };
}

inline float VecDot(Vec3 lhs_vec, Vec3 rhs_vec) {
    return lhs_vec.coord_x * rhs_vec.coord_x +
           lhs_vec.coord_y * rhs_vec.coord_y +
           lhs_vec.coord_z * rhs_vec.coord_z;
}

inline float VecLen(Vec3 vec_in) {
    return std::sqrt(
        vec_in.coord_x * vec_in.coord_x +
        vec_in.coord_y * vec_in.coord_y +
        vec_in.coord_z * vec_in.coord_z);
}

inline Vec3 VecNorm(Vec3 vec_in) {
    float length = VecLen(vec_in);
    if (length <= 1e-7f) {
        return {0.0f, 0.0f, 1.0f};
    }
    float inv_len = 1.0f / length;
    return {vec_in.coord_x * inv_len, vec_in.coord_y * inv_len, vec_in.coord_z * inv_len};
}

inline Vec3 ClampVecLen(Vec3 vec_in, float maxLen) {
    float length = VecLen(vec_in);
    if (length > maxLen && length > 1e-7f) {
        return VecScale(vec_in, maxLen / length);
    }
    return vec_in;
}

inline Vec3 QuatRotateVec(Quat quat_in, Vec3 vec_in) {
    float cross_x =
        quat_in.quat_y * vec_in.coord_z - quat_in.quat_z * vec_in.coord_y +
        quat_in.quat_w * vec_in.coord_x;
    float cross_y =
        quat_in.quat_z * vec_in.coord_x - quat_in.quat_x * vec_in.coord_z +
        quat_in.quat_w * vec_in.coord_y;
    float cross_z =
        quat_in.quat_x * vec_in.coord_y - quat_in.quat_y * vec_in.coord_x +
        quat_in.quat_w * vec_in.coord_z;
    return {
        vec_in.coord_x + 2.0f * (quat_in.quat_y * cross_z - quat_in.quat_z * cross_y),
        vec_in.coord_y + 2.0f * (quat_in.quat_z * cross_x - quat_in.quat_x * cross_z),
        vec_in.coord_z + 2.0f * (quat_in.quat_x * cross_y - quat_in.quat_y * cross_x),
    };
}

inline Quat QuatMul(Quat lhs_quat, Quat rhs_quat) {
    return {
        lhs_quat.quat_w * rhs_quat.quat_x + lhs_quat.quat_x * rhs_quat.quat_w +
            lhs_quat.quat_y * rhs_quat.quat_z - lhs_quat.quat_z * rhs_quat.quat_y,
        lhs_quat.quat_w * rhs_quat.quat_y - lhs_quat.quat_x * rhs_quat.quat_z +
            lhs_quat.quat_y * rhs_quat.quat_w + lhs_quat.quat_z * rhs_quat.quat_x,
        lhs_quat.quat_w * rhs_quat.quat_z + lhs_quat.quat_x * rhs_quat.quat_y -
            lhs_quat.quat_y * rhs_quat.quat_x + lhs_quat.quat_z * rhs_quat.quat_w,
        lhs_quat.quat_w * rhs_quat.quat_w - lhs_quat.quat_x * rhs_quat.quat_x -
            lhs_quat.quat_y * rhs_quat.quat_y - lhs_quat.quat_z * rhs_quat.quat_z,
    };
}

inline Quat QuatConj(Quat quat_in) {
    return {-quat_in.quat_x, -quat_in.quat_y, -quat_in.quat_z, quat_in.quat_w};
}

inline float QuatLen(Quat quat_in) {
    return std::sqrt(
        quat_in.quat_x * quat_in.quat_x + quat_in.quat_y * quat_in.quat_y +
        quat_in.quat_z * quat_in.quat_z + quat_in.quat_w * quat_in.quat_w);
}

inline Quat QuatNorm(Quat quat_in) {
    float length = QuatLen(quat_in);
    if (length <= 1e-8f) {
        return {0.0f, 0.0f, 0.0f, 1.0f};
    }
    float inv_len = 1.0f / length;
    return {
        quat_in.quat_x * inv_len,
        quat_in.quat_y * inv_len,
        quat_in.quat_z * inv_len,
        quat_in.quat_w * inv_len,
    };
}

/** Smoothly spherical-linear-interpolate from identity quaternion to `target`. */
inline Quat QuatSlerpIdentity(Quat target, float blend_factor) {
    if (blend_factor <= 1e-6f) {
        return {0.0f, 0.0f, 0.0f, 1.0f};
    }
    Quat norm_quat = QuatNorm(target);
    if (norm_quat.quat_w < 0.0f) {
        norm_quat = {
            -norm_quat.quat_x,
            -norm_quat.quat_y,
            -norm_quat.quat_z,
            -norm_quat.quat_w,
        };
    }
    if (norm_quat.quat_w >= 0.999999f) {
        return {0.0f, 0.0f, 0.0f, 1.0f};
    }
    float clamped_w =
        (norm_quat.quat_w > 1.0f) ? 1.0f : (norm_quat.quat_w < -1.0f ? -1.0f : norm_quat.quat_w);
    float half_angle = std::acos(clamped_w);
    float sin_half = std::sin(half_angle);
    float scaled_half = half_angle * blend_factor;
    float scale_val = (sin_half > 1e-6f) ? (std::sin(scaled_half) / sin_half) : blend_factor;
    return QuatNorm({
        norm_quat.quat_x * scale_val,
        norm_quat.quat_y * scale_val,
        norm_quat.quat_z * scale_val,
        std::cos(scaled_half),
    });
}

/** Construct shortest-arc rotation quaternion aligning `from_vec` onto `to_vec`. */
inline Quat QuatFromTwoVectors(Vec3 from_vec, Vec3 to_vec) {
    Vec3 norm_from = VecNorm(from_vec);
    Vec3 norm_to = VecNorm(to_vec);
    float dot_val = VecDot(norm_from, norm_to);
    if (dot_val > 1.0f) dot_val = 1.0f;
    if (dot_val < -1.0f) dot_val = -1.0f;
    if (dot_val > 0.999999f) {
        return {0.0f, 0.0f, 0.0f, 1.0f};
    }
    if (dot_val < -0.999999f) {
        Vec3 ortho_ref = (std::fabs(norm_from.coord_x) < 0.9f) ? Vec3{1.0f, 0.0f, 0.0f}
                                                               : Vec3{0.0f, 1.0f, 0.0f};
        Vec3 axis = VecNorm({
            norm_from.coord_y * ortho_ref.coord_z - norm_from.coord_z * ortho_ref.coord_y,
            norm_from.coord_z * ortho_ref.coord_x - norm_from.coord_x * ortho_ref.coord_z,
            norm_from.coord_x * ortho_ref.coord_y - norm_from.coord_y * ortho_ref.coord_x,
        });
        return {axis.coord_x, axis.coord_y, axis.coord_z, 0.0f};
    }
    float axis_x = norm_from.coord_y * norm_to.coord_z - norm_from.coord_z * norm_to.coord_y;
    float axis_y = norm_from.coord_z * norm_to.coord_x - norm_from.coord_x * norm_to.coord_z;
    float axis_z = norm_from.coord_x * norm_to.coord_y - norm_from.coord_y * norm_to.coord_x;
    return QuatNorm({axis_x, axis_y, axis_z, 1.0f + dot_val});
}

/** Extract rotation quaternion from the upper-left 3x3 basis of `Mat34V`. */
inline Quat Mat34ToQuat(const Mat34V& mat_in) {
    Vec3 col_vec0 = VecNorm({mat_in.col0[0], mat_in.col0[1], mat_in.col0[2]});
    Vec3 col_vec1 = VecNorm({mat_in.col1[0], mat_in.col1[1], mat_in.col1[2]});
    Vec3 col_vec2 = VecNorm({mat_in.col2[0], mat_in.col2[1], mat_in.col2[2]});
    float m00 = col_vec0.coord_x, m01 = col_vec1.coord_x, m02 = col_vec2.coord_x;
    float m10 = col_vec0.coord_y, m11 = col_vec1.coord_y, m12 = col_vec2.coord_y;
    float m20 = col_vec0.coord_z, m21 = col_vec1.coord_z, m22 = col_vec2.coord_z;
    float trace = m00 + m11 + m22;
    Quat quat_out{};
    if (trace > 0.0f) {
        float diag_scale = std::sqrt(trace + 1.0f) * 2.0f;
        quat_out.quat_w = 0.25f * diag_scale;
        quat_out.quat_x = (m21 - m12) / diag_scale;
        quat_out.quat_y = (m02 - m20) / diag_scale;
        quat_out.quat_z = (m10 - m01) / diag_scale;
    } else if (m00 > m11 && m00 > m22) {
        float diag_scale = std::sqrt(1.0f + m00 - m11 - m22) * 2.0f;
        quat_out.quat_w = (m21 - m12) / diag_scale;
        quat_out.quat_x = 0.25f * diag_scale;
        quat_out.quat_y = (m01 + m10) / diag_scale;
        quat_out.quat_z = (m02 + m20) / diag_scale;
    } else if (m11 > m22) {
        float diag_scale = std::sqrt(1.0f + m11 - m00 - m22) * 2.0f;
        quat_out.quat_w = (m02 - m20) / diag_scale;
        quat_out.quat_x = (m01 + m10) / diag_scale;
        quat_out.quat_y = 0.25f * diag_scale;
        quat_out.quat_z = (m12 + m21) / diag_scale;
    } else {
        float diag_scale = std::sqrt(1.0f + m22 - m00 - m11) * 2.0f;
        quat_out.quat_w = (m10 - m01) / diag_scale;
        quat_out.quat_x = (m02 + m20) / diag_scale;
        quat_out.quat_y = (m12 + m21) / diag_scale;
        quat_out.quat_z = 0.25f * diag_scale;
    }
    return QuatNorm(quat_out);
}

/** Compose a `Mat34V` transform from unit rotation quaternion `quat_in` and translation `trans_vec`. */
inline Mat34V QuatTransToMat34(Quat quat_in, Vec3 trans_vec) {
    Quat norm_quat = QuatNorm(quat_in);
    float sq_xx = norm_quat.quat_x * norm_quat.quat_x;
    float sq_yy = norm_quat.quat_y * norm_quat.quat_y;
    float sq_zz = norm_quat.quat_z * norm_quat.quat_z;
    float prod_xy = norm_quat.quat_x * norm_quat.quat_y;
    float prod_xz = norm_quat.quat_x * norm_quat.quat_z;
    float prod_yz = norm_quat.quat_y * norm_quat.quat_z;
    float prod_wx = norm_quat.quat_w * norm_quat.quat_x;
    float prod_wy = norm_quat.quat_w * norm_quat.quat_y;
    float prod_wz = norm_quat.quat_w * norm_quat.quat_z;

    Mat34V out_mat{};
    out_mat.col0[0] = 1.0f - 2.0f * (sq_yy + sq_zz);
    out_mat.col0[1] = 2.0f * (prod_xy + prod_wz);
    out_mat.col0[2] = 2.0f * (prod_xz - prod_wy);
    out_mat.col0[3] = 0.0f;

    out_mat.col1[0] = 2.0f * (prod_xy - prod_wz);
    out_mat.col1[1] = 1.0f - 2.0f * (sq_xx + sq_zz);
    out_mat.col1[2] = 2.0f * (prod_yz + prod_wx);
    out_mat.col1[3] = 0.0f;

    out_mat.col2[0] = 2.0f * (prod_xz + prod_wy);
    out_mat.col2[1] = 2.0f * (prod_yz - prod_wx);
    out_mat.col2[2] = 1.0f - 2.0f * (sq_xx + sq_yy);
    out_mat.col2[3] = 0.0f;

    out_mat.col3[0] = trans_vec.coord_x;
    out_mat.col3[1] = trans_vec.coord_y;
    out_mat.col3[2] = trans_vec.coord_z;
    out_mat.col3[3] = 1.0f;
    return out_mat;
}

inline Vec3 TransformPoint(const Mat34V& mat_in, Vec3 point_in) {
    return {
        mat_in.col0[0] * point_in.coord_x + mat_in.col1[0] * point_in.coord_y +
            mat_in.col2[0] * point_in.coord_z + mat_in.col3[0],
        mat_in.col0[1] * point_in.coord_x + mat_in.col1[1] * point_in.coord_y +
            mat_in.col2[1] * point_in.coord_z + mat_in.col3[1],
        mat_in.col0[2] * point_in.coord_x + mat_in.col1[2] * point_in.coord_y +
            mat_in.col2[2] * point_in.coord_z + mat_in.col3[2],
    };
}

inline Mat34V MulMat34(const Mat34V& lhs_mat, const Mat34V& rhs_mat) {
    Mat34V out_mat{};
    for (int col = 0; col < 3; ++col) {
        const float* src_col = (col == 0) ? rhs_mat.col0 : (col == 1 ? rhs_mat.col1 : rhs_mat.col2);
        float* dst_col = (col == 0) ? out_mat.col0 : (col == 1 ? out_mat.col1 : out_mat.col2);
        for (int row = 0; row < 3; ++row) {
            dst_col[row] = lhs_mat.col0[row] * src_col[0] +
                           lhs_mat.col1[row] * src_col[1] +
                           lhs_mat.col2[row] * src_col[2];
        }
        dst_col[3] = 0.0f;
    }
    Vec3 trans_out = TransformPoint(lhs_mat, {rhs_mat.col3[0], rhs_mat.col3[1], rhs_mat.col3[2]});
    out_mat.col3[0] = trans_out.coord_x;
    out_mat.col3[1] = trans_out.coord_y;
    out_mat.col3[2] = trans_out.coord_z;
    out_mat.col3[3] = 1.0f;
    return out_mat;
}

}  // namespace gtav_physbones
