#pragma once
/*
 * gtav_physbones_skeleton.hpp
 * ===========================
 * Layer 3 (Memory & RAGE Skeleton Resolution): Per-pointer SEH memory reads
 * and writes, multi-hop pointer chain discovery (`CPed -> crSkeleton ->
 * crSkeletonData`), structural fingerprinting against known rest bone
 * positions, and the sub-frame synchronization worker thread.
 */

#include "gtav_physbones_config.hpp"

#include <cmath>
#include <cstdint>
#include <cstring>
#include <sstream>

namespace gtav_physbones {

inline CRITICAL_SECTION g_syncLock{};
inline SyncSnapshotList g_syncStateList{};
inline HANDLE g_syncThread = nullptr;
inline volatile LONG g_stopSyncThread = 0;

// ---------------------------------------------------------------------------
// Per-Pointer SEH Memory Guards & Matrix Writes
// ---------------------------------------------------------------------------
inline bool IsCanonicalUserPtr(uint64_t ptr_val) {
    return ptr_val > 0x10000ULL && ptr_val < 0x00007FFFFFFFFFFFULL &&
           ((ptr_val & 0x7ULL) == 0);
}

inline bool IsReadableUserRange(uint64_t ptr_val) {
    return ptr_val > 0x10000ULL && ptr_val < 0x00007FFFFFFFFFFFULL;
}

inline bool SafeReadU64(uint64_t addr, uint64_t& out_val) {
    if (!IsReadableUserRange(addr)) return false;
    __try {
        out_val = *reinterpret_cast<const uint64_t*>(addr);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

inline bool SafeReadU16(uint64_t addr, uint16_t& out_val) {
    if (!IsReadableUserRange(addr)) return false;
    __try {
        out_val = *reinterpret_cast<const uint16_t*>(addr);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

inline bool SafeReadMat34(uint64_t addr, Mat34V& out_mat) {
    if (!IsReadableUserRange(addr)) return false;
    __try {
        std::memcpy(&out_mat, reinterpret_cast<const void*>(addr), sizeof(Mat34V));
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

inline bool SafeReadVec3(uint64_t addr, Vec3& out_vec) {
    if (!IsReadableUserRange(addr)) return false;
    __try {
        const float* float_ptr = reinterpret_cast<const float*>(addr);
        out_vec.coord_x = float_ptr[0];
        out_vec.coord_y = float_ptr[1];
        out_vec.coord_z = float_ptr[2];
        return std::isfinite(out_vec.coord_x) && std::isfinite(out_vec.coord_y) &&
               std::isfinite(out_vec.coord_z);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

inline bool SafeReadQuat(uint64_t addr, Quat& out_quat) {
    if (!IsReadableUserRange(addr)) return false;
    __try {
        const float* float_ptr = reinterpret_cast<const float*>(addr);
        out_quat.quat_x = float_ptr[0];
        out_quat.quat_y = float_ptr[1];
        out_quat.quat_z = float_ptr[2];
        out_quat.quat_w = float_ptr[3];
        return std::isfinite(out_quat.quat_x) && std::isfinite(out_quat.quat_y) &&
               std::isfinite(out_quat.quat_z) && std::isfinite(out_quat.quat_w);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

/** Validate finite basis columns with realistic near-unit scale. */
inline bool IsValidMat34(const Mat34V& mat_in) {
    if (!std::isfinite(mat_in.col0[0]) || !std::isfinite(mat_in.col0[1]) ||
        !std::isfinite(mat_in.col0[2]) || !std::isfinite(mat_in.col1[0]) ||
        !std::isfinite(mat_in.col1[1]) || !std::isfinite(mat_in.col1[2]) ||
        !std::isfinite(mat_in.col2[0]) || !std::isfinite(mat_in.col2[1]) ||
        !std::isfinite(mat_in.col2[2]) || !std::isfinite(mat_in.col3[0]) ||
        !std::isfinite(mat_in.col3[1]) || !std::isfinite(mat_in.col3[2])) {
        return false;
    }
    float len0 = VecLen({mat_in.col0[0], mat_in.col0[1], mat_in.col0[2]});
    float len1 = VecLen({mat_in.col1[0], mat_in.col1[1], mat_in.col1[2]});
    float len2 = VecLen({mat_in.col2[0], mat_in.col2[1], mat_in.col2[2]});
    return len0 > 0.7f && len0 < 1.3f && len1 > 0.7f && len1 < 1.3f &&
           len2 > 0.7f && len2 < 1.3f;
}

/** Atomically push local/object matrices and crBoneData default transforms inside SEH. */
inline bool SafeWriteSkeletonBatch(
    ResolvedSkeleton& skel,
    const int* skelIndices,
    const Mat34V* localMatrices,
    const Mat34V* objectMatrices,
    const Quat* localQuats,
    size_t count,
    bool writeBoneTrans = false
) {
    __try {
        int boneTransOff = (skel.boneDataRotOff == 0) ? 0x10 : 0x00;
        for (size_t idx = 0; idx < count; ++idx) {
            int boneIdx = skelIndices[idx];
            if (boneIdx < 0 || static_cast<uint32_t>(boneIdx) >= skel.numBones) continue;
            if (skel.defaultTransforms) {
                skel.defaultTransforms[boneIdx] = localMatrices[idx];
            }
            if (skel.boneDataArray && skel.boneDataRotOff >= 0) {
                uint8_t* boneEntry =
                    skel.boneDataArray + static_cast<size_t>(boneIdx) * skel.boneDataStride;
                Quat* defRot = reinterpret_cast<Quat*>(boneEntry + skel.boneDataRotOff);
                *defRot = localQuats[idx];
                if (writeBoneTrans) {
                    Vec3* defTrans = reinterpret_cast<Vec3*>(boneEntry + boneTransOff);
                    defTrans->coord_x = localMatrices[idx].col3[0];
                    defTrans->coord_y = localMatrices[idx].col3[1];
                    defTrans->coord_z = localMatrices[idx].col3[2];
                }
            }
            skel.localMatrices[boneIdx] = localMatrices[idx];
            skel.objectMatrices[boneIdx] = objectMatrices[idx];
        }
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

/**
 * Re-apply cached bone matrices on the 1 ms background sync worker thread
 * so RAGE animation/expression evaluation cannot clobber PhysBones or blinks
 * between script fiber ticks.
 */
inline bool SafeApplySyncSnapshot(const SyncSnapshot& snap) {
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
            float delta_x = refMtx.col3[0] - snap.refPosA.coord_x;
            float delta_y = refMtx.col3[1] - snap.refPosA.coord_y;
            float delta_z = refMtx.col3[2] - snap.refPosA.coord_z;
            if (delta_x * delta_x + delta_y * delta_y + delta_z * delta_z > 0.01f) {
                return false;
            }
        }

        Mat34V* defMats = reinterpret_cast<Mat34V*>(snap.defaultTransforms);
        uint8_t* boneArr = reinterpret_cast<uint8_t*>(snap.boneDataArray);
        int boneTransOff = (snap.boneDataRotOff == 0) ? 0x10 : 0x00;

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
                    uint8_t* boneEntry =
                        boneArr + static_cast<size_t>(boneIdx) * snap.boneDataStride;
                    Quat* defRot = reinterpret_cast<Quat*>(boneEntry + snap.boneDataRotOff);
                    *defRot = snap.localQuat[idx];
                    if (snap.writeDefault[idx] >= 2) {
                        Vec3* defTrans = reinterpret_cast<Vec3*>(boneEntry + boneTransOff);
                        defTrans->coord_x = snap.localMat[idx].col3[0];
                        defTrans->coord_y = snap.localMat[idx].col3[1];
                        defTrans->coord_z = snap.localMat[idx].col3[2];
                    }
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

/** Sub-frame sync worker running alongside the ScriptHookV fiber loop. */
inline DWORD WINAPI SyncThreadProc(LPVOID /*param*/) {
    static SyncSnapshotList localCopy{};
    while (InterlockedCompareExchange(&g_stopSyncThread, 0, 0) == 0) {
        EnterCriticalSection(&g_syncLock);
        localCopy = g_syncStateList;
        LeaveCriticalSection(&g_syncLock);

        for (int slot_idx = 0;
             slot_idx < localCopy.slotCount && slot_idx < kMaxTrackedPeds;
             ++slot_idx) {
            if (localCopy.slots[slot_idx].active) {
                SafeApplySyncSnapshot(localCopy.slots[slot_idx]);
            }
        }
        Sleep(1);
    }
    return 0;
}

// ---------------------------------------------------------------------------
// RAGE crSkeleton / crSkeletonData Layout Fingerprinting & Validation
// ---------------------------------------------------------------------------
/** Locate `m_defaultTransforms` and `crBoneData[]` inside `crSkeletonData`. */
inline void ProbeSkeletonData(
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
        uint64_t cand_ptr = 0;
        if (!SafeReadU64(skelDataPtr + off, cand_ptr) || !IsCanonicalUserPtr(cand_ptr)) continue;
        if (cand_ptr == reinterpret_cast<uint64_t>(outSkel.localMatrices) ||
            cand_ptr == reinterpret_cast<uint64_t>(outSkel.objectMatrices)) {
            continue;
        }

        // Check if cand_ptr points to crSkeletonData::m_defaultTransforms (Mat34V[numBones])
        if (!outSkel.defaultTransforms) {
            Mat34V mat_a{}, mat_b{};
            if (SafeReadMat34(cand_ptr + static_cast<uint64_t>(refA.skelIndex) * sizeof(Mat34V), mat_a) &&
                SafeReadMat34(cand_ptr + static_cast<uint64_t>(refB.skelIndex) * sizeof(Mat34V), mat_b)) {
                Vec3 pos_a{mat_a.col3[0], mat_a.col3[1], mat_a.col3[2]};
                Vec3 pos_b{mat_b.col3[0], mat_b.col3[1], mat_b.col3[2]};
                float col0_len = VecLen({mat_a.col0[0], mat_a.col0[1], mat_a.col0[2]});
                if (col0_len > 0.85f && col0_len < 1.15f &&
                    VecLen(VecSub(pos_a, refA.expectedLocalPos)) < 0.03f &&
                    VecLen(VecSub(pos_b, refB.expectedLocalPos)) < 0.03f) {
                    outSkel.defaultTransforms = reinterpret_cast<Mat34V*>(cand_ptr);
                    outSkel.defaultTransformsOff = off;
                    continue;
                }
            }
        }

        // Check if cand_ptr points to crBoneData[numBones] (stride 0x50)
        if (!outSkel.boneDataArray) {
            constexpr uint64_t stride = 0x50;
            uint64_t entryA = cand_ptr + static_cast<uint64_t>(refA.skelIndex) * stride;
            uint64_t entryB = cand_ptr + static_cast<uint64_t>(refB.skelIndex) * stride;

            Vec3 pos_a{}, pos_b{};
            Quat quat_a{};
            if (SafeReadVec3(entryA + 0x00, pos_a) && SafeReadVec3(entryB + 0x00, pos_b) &&
                VecLen(VecSub(pos_a, refA.expectedLocalPos)) < 0.03f &&
                VecLen(VecSub(pos_b, refB.expectedLocalPos)) < 0.03f &&
                SafeReadQuat(entryA + 0x10, quat_a) && std::fabs(QuatLen(quat_a) - 1.0f) < 0.05f) {
                outSkel.boneDataArray = reinterpret_cast<uint8_t*>(cand_ptr);
                outSkel.boneDataOff = off;
                outSkel.boneDataRotOff = 0x10;
                outSkel.boneDataStride = static_cast<int>(stride);
                continue;
            }
            if (SafeReadVec3(entryA + 0x10, pos_a) && SafeReadVec3(entryB + 0x10, pos_b) &&
                VecLen(VecSub(pos_a, refA.expectedLocalPos)) < 0.03f &&
                VecLen(VecSub(pos_b, refB.expectedLocalPos)) < 0.03f &&
                SafeReadQuat(entryA + 0x00, quat_a) && std::fabs(QuatLen(quat_a) - 1.0f) < 0.05f) {
                outSkel.boneDataArray = reinterpret_cast<uint8_t*>(cand_ptr);
                outSkel.boneDataOff = off;
                outSkel.boneDataRotOff = 0x00;
                outSkel.boneDataStride = static_cast<int>(stride);
                continue;
            }
        }
    }
}

/** Verify which array of the candidate `crSkeleton` holds local vs object-space matrices. */
inline bool ValidateMatPairLayout(
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
        Mat34V mat_a{}, mat_b{};
        if (SafeReadMat34(localCandPtr + static_cast<uint64_t>(refA.skelIndex) * sizeof(Mat34V), mat_a) &&
            SafeReadMat34(localCandPtr + static_cast<uint64_t>(refB.skelIndex) * sizeof(Mat34V), mat_b)) {
            Vec3 pos_a{mat_a.col3[0], mat_a.col3[1], mat_a.col3[2]};
            Vec3 pos_b{mat_b.col3[0], mat_b.col3[1], mat_b.col3[2]};
            if (IsValidMat34(mat_a) && IsValidMat34(mat_b) &&
                VecLen(VecSub(pos_a, refA.expectedLocalPos)) < 0.03f &&
                VecLen(VecSub(pos_b, refB.expectedLocalPos)) < 0.03f) {
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

inline bool ValidateCandidateCrSkeleton(
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
    if (IsCanonicalUserPtr(parentMtxPtr) && SafeReadMat34(parentMtxPtr, entMtx) &&
        IsValidMat34(entMtx)) {
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
    if (ValidateMatPairLayout(
            arr1Ptr, arr2Ptr, numBones, entMtx, entOrigin, headIdx, refA, refB,
            expectedEntityPos, expectedHeadWorldPos)) {
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

    if (ValidateMatPairLayout(
            arr2Ptr, arr1Ptr, numBones, entMtx, entOrigin, headIdx, refA, refB,
            expectedEntityPos, expectedHeadWorldPos)) {
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

inline void DumpPedPointerDiagnostics(
    uint8_t* pedAddr,
    const Vec3& entPos,
    const Vec3& headPos,
    const ProbeRefBone& refA,
    const ProbeRefBone& refB
) {
    uint64_t base_addr = reinterpret_cast<uint64_t>(pedAddr);
    std::ostringstream oss;
    oss << "[DIAG] ped=0x" << std::hex << base_addr << std::dec
        << " ent=(" << entPos.coord_x << "," << entPos.coord_y << "," << entPos.coord_z << ")"
        << " head=(" << headPos.coord_x << "," << headPos.coord_y << "," << headPos.coord_z << ")"
        << " refA=" << refA.skelIndex << " refB=" << refB.skelIndex;
    WriteLog(oss.str());

    std::ostringstream ptrLine;
    ptrLine << "[DIAG] ped+0x20..0x80:";
    for (int off = 0x20; off <= 0x80; off += 8) {
        uint64_t val = 0;
        if (SafeReadU64(base_addr + off, val)) {
            ptrLine << " +0x" << std::hex << off << "=0x" << val;
        }
    }
    WriteLog(ptrLine.str());

    uint64_t ptr_30 = 0;
    if (SafeReadU64(base_addr + 0x30, ptr_30) && IsCanonicalUserPtr(ptr_30)) {
        std::ostringstream p30Line;
        p30Line << "[DIAG] p30(0x" << std::hex << ptr_30 << ")+0x00..0x80:";
        for (int off = 0x00; off <= 0x80; off += 8) {
            uint64_t val = 0;
            if (SafeReadU64(ptr_30 + off, val)) {
                p30Line << " +0x" << off << "=0x" << val;
            }
        }
        WriteLog(p30Line.str());
    }
}

inline bool FollowResolvedHopPath(
    uint64_t pedBase,
    const ResolvedSkeleton& skel,
    uint64_t& outCrSkel
) {
    outCrSkel = 0;
    if (!IsCanonicalUserPtr(pedBase) || skel.hopCount < 1 || skel.hopCount > 3 || skel.off1 < 0) {
        return false;
    }
    uint64_t hop_ptr = 0;
    if (!SafeReadU64(pedBase + static_cast<uint64_t>(skel.off1), hop_ptr) ||
        !IsCanonicalUserPtr(hop_ptr)) {
        return false;
    }
    if (skel.hopCount == 1) {
        outCrSkel = hop_ptr;
        return true;
    }
    if (skel.off2 < 0 ||
        !SafeReadU64(hop_ptr + static_cast<uint64_t>(skel.off2), hop_ptr) ||
        !IsCanonicalUserPtr(hop_ptr)) {
        return false;
    }
    if (skel.hopCount == 2) {
        outCrSkel = hop_ptr;
        return true;
    }
    if (skel.off3 < 0 ||
        !SafeReadU64(hop_ptr + static_cast<uint64_t>(skel.off3), hop_ptr) ||
        !IsCanonicalUserPtr(hop_ptr)) {
        return false;
    }
    outCrSkel = hop_ptr;
    return true;
}

inline bool GetLiveEntityMatrix(uint64_t pedBase, ResolvedSkeleton& skel, Mat34V& outEntMtx) {
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

inline bool IsResolvedSkeletonStillValid(
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
        if (!SafeReadU64(curSkelData + static_cast<uint64_t>(skel.defaultTransformsOff),
                         curDefTransforms) ||
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
            !SafeReadMat34(cachedObj + static_cast<uint64_t>(skel.headIndex) * sizeof(Mat34V),
                           headObj) ||
            !IsValidMat34(headObj)) {
            return false;
        }
        if (VecLen({headObj.col3[0], headObj.col3[1], headObj.col3[2]}) >= 5.0f) {
            return false;
        }
    }

    if (refA.skelIndex >= 0 && static_cast<uint32_t>(refA.skelIndex) < curNumBones) {
        Mat34V mat_a{};
        if (!SafeReadMat34(cachedLoc + static_cast<uint64_t>(refA.skelIndex) * sizeof(Mat34V),
                           mat_a) ||
            !IsValidMat34(mat_a)) {
            return false;
        }
        Vec3 pos_a{mat_a.col3[0], mat_a.col3[1], mat_a.col3[2]};
        if (VecLen(VecSub(pos_a, refA.expectedLocalPos)) > 0.05f) {
            return false;
        }
    }
    if (refB.skelIndex >= 0 && static_cast<uint32_t>(refB.skelIndex) < curNumBones) {
        Mat34V mat_b{};
        if (!SafeReadMat34(cachedLoc + static_cast<uint64_t>(refB.skelIndex) * sizeof(Mat34V),
                           mat_b) ||
            !IsValidMat34(mat_b)) {
            return false;
        }
        Vec3 pos_b{mat_b.col3[0], mat_b.col3[1], mat_b.col3[2]};
        if (VecLen(VecSub(pos_b, refB.expectedLocalPos)) > 0.05f) {
            return false;
        }
    }
    return true;
}

inline bool TryResolveCandidate(
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
    if (!ValidateCandidateCrSkeleton(
            pedBase, candSkel, headIdx, refA, refB, entPos, headPos, outSkel)) {
        return false;
    }
    outSkel.pedAddr = reinterpret_cast<uint8_t*>(pedBase);
    outSkel.hopCount = hopCount;
    outSkel.off1 = off1;
    outSkel.off2 = off2;
    outSkel.off3 = off3;
    return true;
}

/**
 * Discover `rage::crSkeleton` for a live ped via known GTA V Legacy fast paths
 * first, falling back to bounded 1-, 2-, and 3-hop pointer scans when allowed.
 */
inline bool TryResolvePedSkeleton(
    int ped,
    int headIdx,
    const ProbeRefBone& refA,
    const ProbeRefBone& refB,
    bool allowHeavyScan,
    ResolvedSkeleton& outSkel
) {
    uint8_t* pedAddr = g_shv.getEntityAddress(ped);
    uint64_t base_addr = reinterpret_cast<uint64_t>(pedAddr);
    if (!IsCanonicalUserPtr(base_addr) || headIdx < 0) return false;

    Vec3 entPos = CallGetEntityCoords(ped);
    Vec3 headPos = CallGetPedBoneCoords(ped, kSkelHeadTag);

    // 0. Fast-path known GTA V CPed -> ped+0x50 -> +0x30 -> +0x20 crSkeleton chain
    uint64_t ptr_50 = 0;
    if (SafeReadU64(base_addr + 0x50, ptr_50) && IsCanonicalUserPtr(ptr_50)) {
        uint64_t ptr_50_30 = 0;
        if (SafeReadU64(ptr_50 + 0x30, ptr_50_30) && IsCanonicalUserPtr(ptr_50_30)) {
            uint64_t cand20 = 0;
            if (SafeReadU64(ptr_50_30 + 0x20, cand20) &&
                TryResolveCandidate(
                    base_addr, cand20, headIdx, refA, refB, entPos, headPos,
                    3, 0x50, 0x30, 0x20, outSkel)) {
                return true;
            }
            for (int skelOff = 0x10; skelOff <= 0x40; skelOff += 8) {
                if (skelOff == 0x20) continue;
                uint64_t cand = 0;
                if (SafeReadU64(ptr_50_30 + skelOff, cand) &&
                    TryResolveCandidate(
                        base_addr, cand, headIdx, refA, refB, entPos, headPos,
                        3, 0x50, 0x30, skelOff, outSkel)) {
                    return true;
                }
            }
        }
    }

    // 1. Check standard RAGE path: ped+0x30 (fragInst) -> +0x68 (fragCacheEntry) -> +0x100..0x220
    uint64_t fragInst = 0;
    if (SafeReadU64(base_addr + 0x30, fragInst) && IsCanonicalUserPtr(fragInst)) {
        uint64_t midPtr = 0;
        if (SafeReadU64(fragInst + 0x68, midPtr) && IsCanonicalUserPtr(midPtr)) {
            for (int skelOff = 0x100; skelOff <= 0x220; skelOff += 8) {
                uint64_t cand = 0;
                if (SafeReadU64(midPtr + skelOff, cand) &&
                    TryResolveCandidate(
                        base_addr, cand, headIdx, refA, refB, entPos, headPos,
                        3, 0x30, 0x68, skelOff, outSkel)) {
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
        uint64_t ptr_hop1 = 0;
        if (!SafeReadU64(base_addr + off1, ptr_hop1) || !IsCanonicalUserPtr(ptr_hop1)) continue;
        if (TryResolveCandidate(
                base_addr, ptr_hop1, headIdx, refA, refB, entPos, headPos,
                1, off1, -1, -1, outSkel)) {
            return true;
        }
    }

    // 3. 2-hop scan across pedAddr + 0x08..0x300 -> +0x00..0x280
    for (int off1 = 0x08; off1 <= 0x300; off1 += 8) {
        uint64_t ptr_hop1 = 0;
        if (!SafeReadU64(base_addr + off1, ptr_hop1) || !IsCanonicalUserPtr(ptr_hop1)) continue;
        for (int off2 = 0x00; off2 <= 0x280; off2 += 8) {
            uint64_t ptr_hop2 = 0;
            if (!SafeReadU64(ptr_hop1 + off2, ptr_hop2) || !IsCanonicalUserPtr(ptr_hop2)) continue;
            if (TryResolveCandidate(
                    base_addr, ptr_hop2, headIdx, refA, refB, entPos, headPos,
                    2, off1, off2, -1, outSkel)) {
                return true;
            }
        }
    }

    // 4. 3-hop scan across entity component slots
    for (int off1 = 0x08; off1 <= 0x180; off1 += 8) {
        uint64_t ptr_hop1 = 0;
        if (!SafeReadU64(base_addr + off1, ptr_hop1) || !IsCanonicalUserPtr(ptr_hop1)) continue;
        for (int off2 = 0x00; off2 <= 0x100; off2 += 8) {
            uint64_t ptr_hop2 = 0;
            if (!SafeReadU64(ptr_hop1 + off2, ptr_hop2) || !IsCanonicalUserPtr(ptr_hop2)) continue;
            for (int off3 = 0x00; off3 <= 0x280; off3 += 8) {
                uint64_t ptr_hop3 = 0;
                if (!SafeReadU64(ptr_hop2 + off3, ptr_hop3) || !IsCanonicalUserPtr(ptr_hop3)) {
                    continue;
                }
                if (TryResolveCandidate(
                        base_addr, ptr_hop3, headIdx, refA, refB, entPos, headPos,
                        3, off1, off2, off3, outSkel)) {
                    return true;
                }
            }
        }
    }

    return false;
}

}  // namespace gtav_physbones
