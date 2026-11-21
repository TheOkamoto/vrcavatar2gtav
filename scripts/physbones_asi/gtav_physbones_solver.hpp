#pragma once
/*
 * gtav_physbones_solver.hpp
 * =========================
 * Layer 4 (Physics & Eye Blink Solver): Underdamped filtered Verlet PhysBone
 * integration, VRChat Advanced (`integrationType == 1`) parent-relative
 * stiffness restraint, cone angle limit solver, natural asymmetrical eyelid
 * blink curve evaluation, and sync snapshot assembly.
 */

#include "gtav_physbones_skeleton.hpp"

#include <cmath>
#include <cstdint>
#include <sstream>
#include <vector>

namespace gtav_physbones {

// ---------------------------------------------------------------------------
// VRCPhysBone Verlet + Advanced Stiffness Solver
// ---------------------------------------------------------------------------
/**
 * Advance one PhysBone chain by `deltaTime`, writing updated local matrices,
 * object-space matrices, and local quaternions for all bones in the chain.
 */
inline void ComputeChainMatrices(
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
    const size_t node_count = chain.bones.size();
    if (node_count < 2 || node_count > kMaxBonesPerChain) return;

    const Vec3 entWorldPos{
        entityWorldMtx.col3[0], entityWorldMtx.col3[1], entityWorldMtx.col3[2]};
    const Mat34V parentWorldMtx = MulMat34(entityWorldMtx, parentObjMtx);
    const Vec3 parentWorldPos{
        parentWorldMtx.col3[0], parentWorldMtx.col3[1], parentWorldMtx.col3[2]};
    const Quat parentWorldRot = Mat34ToQuat(parentWorldMtx);

    Vec3 posePos[kMaxBonesPerChain]{};
    Vec3 curPos = parentWorldPos;
    Quat curRot = parentWorldRot;
    for (size_t idx = 0; idx < node_count; ++idx) {
        curPos = VecAdd(curPos, QuatRotateVec(curRot, chain.bones[idx].localPos));
        curRot = QuatNorm(QuatMul(curRot, chain.bones[idx].localRot));
        posePos[idx] = curPos;
    }

    Vec3 rootStepDelta = VecSub(posePos[0], chain.prevRootWorldPos);
    Vec3 prevRelRoot = VecSub(chain.prevRootWorldPos, chain.prevEntWorldPos);
    Vec3 curRelRoot = VecSub(posePos[0], entWorldPos);
    Vec3 relRootDelta = VecSub(curRelRoot, prevRelRoot);
    if (!chain.initialized || VecLen(rootStepDelta) > 12.0f || VecLen(relRootDelta) > 0.85f) {
        chain.worldPos.assign(posePos, posePos + node_count);
        chain.prevWorldPos.assign(posePos, posePos + node_count);
        chain.prevPosePos.assign(posePos, posePos + node_count);
        chain.prevEntWorldPos = entWorldPos;
        chain.prevRootWorldPos = posePos[0];
        chain.smoothedRootVel = {0.0f, 0.0f, 0.0f};
        chain.initialized = true;
    } else {
        float clampedDt = (deltaTime < 1e-4f)
                              ? 1e-4f
                              : (deltaTime > g_cfg.maxDeltaTime ? g_cfg.maxDeltaTime : deltaTime);
        float invDt = 1.0f / clampedDt;
        Vec3 instRootVel = VecScale(rootStepDelta, invDt);

        // Separate steady locomotion/fall velocity (~0.18s EMA) from clamped step-bob impulses
        float emaAlpha = clampedDt / 0.18f;
        if (emaAlpha > 1.0f) emaAlpha = 1.0f;
        chain.smoothedRootVel = VecAdd(
            VecScale(chain.smoothedRootVel, 1.0f - emaAlpha),
            VecScale(instRootVel, emaAlpha));
        Vec3 steadyShift = VecScale(chain.smoothedRootVel, clampedDt);
        Vec3 oscRootDelta = ClampVecLen(VecSub(rootStepDelta, steadyShift), 0.06f);
        chain.prevEntWorldPos = entWorldPos;
        chain.prevRootWorldPos = posePos[0];

        float immobileScale =
            (chain.immobile < 0.0f) ? 0.0f : (chain.immobile > 1.0f ? 1.0f : chain.immobile);
        Vec3 immobileShift = VecAdd(steadyShift, VecScale(oscRootDelta, immobileScale));

        float rateScale = clampedDt * 60.0f;
        float springClamped =
            (chain.spring < 0.0f) ? 0.0f : (chain.spring > 1.0f ? 1.0f : chain.spring);
        float velBase = 0.88f + 0.05f * springClamped;
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
        float gravFalloffClamped = (chain.gravityFalloff < 0.0f)
                                       ? 0.0f
                                       : (chain.gravityFalloff > 1.0f ? 1.0f : chain.gravityFalloff);
        float effGravity = chain.gravity * (1.0f - gravFalloffClamped);
        for (size_t idx = 1; idx < node_count; ++idx) {
            Vec3 nodeOscDelta =
                ClampVecLen(VecSub(VecSub(posePos[idx], chain.prevPosePos[idx]), steadyShift), 0.06f);
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

    // Stage 2: Angle cone limit constraints + Advanced stiffness + segment length clamp
    Quat worldRotOut[kMaxBonesPerChain]{};
    for (size_t idx = 0; idx + 1 < node_count; ++idx) {
        Vec3 nodePos = chain.worldPos[idx];
        Vec3 childPos = chain.worldPos[idx + 1];
        Vec3 curDir = VecNorm(VecSub(childPos, nodePos));

        Quat expParentRot = (idx == 0) ? parentWorldRot : worldRotOut[idx - 1];
        Quat restNodeRot = QuatNorm(QuatMul(expParentRot, chain.bones[idx].localRot));
        Vec3 restSegDir = VecNorm(QuatRotateVec(restNodeRot, chain.bones[idx + 1].localPos));

        // VRChat Advanced PhysBones (integrationType == 1): stiffness resists bending from rest
        if (chain.integrationType == 1 && chain.stiffness > 0.001f) {
            float dtClamped = (deltaTime < 1e-4f)
                                  ? 1e-4f
                                  : (deltaTime > g_cfg.maxDeltaTime ? g_cfg.maxDeltaTime : deltaTime);
            float stiffClamped =
                (chain.stiffness < 0.0f) ? 0.0f : (chain.stiffness > 1.0f ? 1.0f : chain.stiffness);
            float stiffFactor = 1.0f - std::pow(1.0f - stiffClamped * 0.35f, dtClamped * 60.0f);
            curDir = VecNorm(
                VecAdd(VecScale(curDir, 1.0f - stiffFactor), VecScale(restSegDir, stiffFactor)));
        }

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
    worldRotOut[node_count - 1] =
        QuatNorm(QuatMul(worldRotOut[node_count - 2], chain.bones[node_count - 1].localRot));

    const Quat entWorldRotInv = QuatConj(Mat34ToQuat(entityWorldMtx));

    for (size_t idx = 0; idx < node_count; ++idx) {
        Quat parentBoneWorldRot = (idx == 0) ? parentWorldRot : worldRotOut[idx - 1];
        Quat locRot = QuatNorm(QuatMul(QuatConj(parentBoneWorldRot), worldRotOut[idx]));
        outLocalQuats[idx] = locRot;
        outLocalMatrices[idx] = QuatTransToMat34(locRot, chain.bones[idx].localPos);

        Vec3 objPos = QuatRotateVec(entWorldRotInv, VecSub(chain.worldPos[idx], entWorldPos));
        Quat objRot = QuatNorm(QuatMul(entWorldRotInv, worldRotOut[idx]));
        outObjectMatrices[idx] = QuatTransToMat34(objRot, objPos);
    }
    outCount = node_count;
}

// ---------------------------------------------------------------------------
// Natural Eyelid Blink State Machine
// ---------------------------------------------------------------------------
inline float NextBlinkRand01(BlinkRuntimeState& blink_state) {
    uint32_t seed_val = blink_state.rngState ? blink_state.rngState : 0x9E3779B9U;
    seed_val ^= seed_val << 13;
    seed_val ^= seed_val >> 17;
    seed_val ^= seed_val << 5;
    blink_state.rngState = seed_val;
    return static_cast<float>(seed_val & 0x00FFFFFFU) / static_cast<float>(0x01000000U);
}

/** Asymmetric blink envelope: brisk closure (0..28%), short hold, smooth opening. */
inline float EvaluateNaturalBlinkCurve(float elapsed, float duration) {
    if (duration <= 0.01f) return 0.0f;
    float norm_time = elapsed / duration;
    if (norm_time <= 0.0f || norm_time >= 1.0f) return 0.0f;
    constexpr float kCloseEnd = 0.28f;
    constexpr float kHoldEnd = 0.40f;
    if (norm_time < kCloseEnd) {
        float close_ratio = norm_time / kCloseEnd;
        return close_ratio * close_ratio * (3.0f - 2.0f * close_ratio);
    }
    if (norm_time < kHoldEnd) {
        return 1.0f;
    }
    float open_ratio = (norm_time - kHoldEnd) / (1.0f - kHoldEnd);
    float eased_val = open_ratio * (2.0f - open_ratio);
    float blink_amt = 1.0f - (eased_val * eased_val * (3.0f - 2.0f * eased_val));
    return (blink_amt < 0.0f) ? 0.0f : ((blink_amt > 1.0f) ? 1.0f : blink_amt);
}

inline const BlinkProfile* FindMatchingBlinkProfile(
    const std::vector<BlinkProfile>& profiles,
    uint32_t modelHash
) {
    const BlinkProfile* fallback = nullptr;
    for (const BlinkProfile& blink_prof : profiles) {
        if (!blink_prof.enabled || blink_prof.bones.empty()) continue;
        if (blink_prof.modelHash != 0U && blink_prof.modelHash == modelHash) {
            return &blink_prof;
        }
        if ((blink_prof.model.empty() || blink_prof.model == "all") && !fallback) {
            fallback = &blink_prof;
        }
    }
    return fallback;
}

inline float UpdatePedBlinkAmount(
    TrackedPedSlot& slot,
    const BlinkProfile& blink_prof,
    float deltaTime
) {
    BlinkRuntimeState& blink_state = slot.blinkState;
    if (!blink_state.initialized) {
        uint64_t ptrVal = reinterpret_cast<uintptr_t>(slot.pedAddr);
        blink_state.rngState = static_cast<uint32_t>((ptrVal >> 3) ^ slot.modelHash ^ 0xA5A55A5AU);
        if (blink_state.rngState == 0U) blink_state.rngState = 0x9E3779B9U;
        blink_state.nextDelay = 0.5f + NextBlinkRand01(blink_state) * 2.5f;
        blink_state.waitTimer = 0.0f;
        blink_state.blinking = false;
        blink_state.doubleBlinkPending = false;
        blink_state.blinkElapsed = 0.0f;
        blink_state.initialized = true;
    }

    if (CallIsEntityDead(slot.pedHandle)) {
        blink_state.blinking = false;
        blink_state.doubleBlinkPending = false;
        blink_state.blinkElapsed = 0.0f;
        return 0.0f;
    }

    float blinkDt = (deltaTime < 0.0f)
                        ? 0.0f
                        : ((deltaTime > g_cfg.maxDeltaTime) ? g_cfg.maxDeltaTime : deltaTime);
    if (blink_state.blinking) {
        blink_state.blinkElapsed += blinkDt;
        if (blink_state.blinkElapsed >= blink_prof.blinkDuration) {
            blink_state.blinking = false;
            blink_state.blinkElapsed = 0.0f;
            blink_state.waitTimer = 0.0f;
            if (!blink_state.doubleBlinkPending &&
                NextBlinkRand01(blink_state) < blink_prof.doubleBlinkChance) {
                blink_state.doubleBlinkPending = true;
                blink_state.nextDelay = 0.11f + NextBlinkRand01(blink_state) * 0.06f;
            } else {
                blink_state.doubleBlinkPending = false;
                float uMix = 0.5f * (NextBlinkRand01(blink_state) + NextBlinkRand01(blink_state));
                blink_state.nextDelay =
                    blink_prof.minInterval + uMix * (blink_prof.maxInterval - blink_prof.minInterval);
            }
            return 0.0f;
        }
        return EvaluateNaturalBlinkCurve(blink_state.blinkElapsed, blink_prof.blinkDuration) *
               blink_prof.maxBlink;
    }

    blink_state.waitTimer += blinkDt;
    if (blink_state.waitTimer >= blink_state.nextDelay) {
        blink_state.blinking = true;
        blink_state.blinkElapsed = 0.0f;
        blink_state.waitTimer = 0.0f;
    }
    return 0.0f;
}

// ---------------------------------------------------------------------------
// Per-Ped Frame Simulation & SyncSnapshot Publishing
// ---------------------------------------------------------------------------
inline void UpdatePedChainsAndBuildSync(
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

    for (auto& chain_ref : slot.chains) {
        if (chain_ref.bones.size() < 2 ||
            chain_ref.bones.size() > static_cast<size_t>(kMaxBonesPerChain)) {
            continue;
        }
        bool allBonesValid = true;
        for (const auto& bone_node : chain_ref.bones) {
            if (bone_node.skelIndex < 0 ||
                static_cast<uint32_t>(bone_node.skelIndex) >= slot.skel.numBones) {
                allBonesValid = false;
                break;
            }
        }
        if (!allBonesValid) continue;

        Mat34V parentObjMtx{};
        if (chain_ref.parentSkelIndex < 0 ||
            static_cast<uint32_t>(chain_ref.parentSkelIndex) >= slot.skel.numBones) {
            continue;
        }
        if (!SafeReadMat34(
                reinterpret_cast<uint64_t>(slot.skel.objectMatrices) +
                    static_cast<uint64_t>(chain_ref.parentSkelIndex) * sizeof(Mat34V),
                parentObjMtx) ||
            !IsValidMat34(parentObjMtx)) {
            continue;
        }

        Mat34V localMats[kMaxBonesPerChain]{};
        Mat34V objMats[kMaxBonesPerChain]{};
        Quat localQuats[kMaxBonesPerChain]{};
        size_t outCount = 0;
        ComputeChainMatrices(
            chain_ref, entityWorldMtx, parentObjMtx, deltaTime,
            localMats, objMats, localQuats, outCount);
        if (outCount == 0) continue;

        bool finiteMatrices = true;
        for (size_t idx = 0; idx < outCount; ++idx) {
            if (!IsValidMat34(localMats[idx]) || !IsValidMat34(objMats[idx])) {
                finiteMatrices = false;
                break;
            }
        }
        if (!finiteMatrices) {
            chain_ref.initialized = false;
            continue;
        }

        int indices[kMaxBonesPerChain]{};
        for (size_t idx = 0; idx < outCount; ++idx) {
            indices[idx] = chain_ref.bones[idx].skelIndex;
        }
        SafeWriteSkeletonBatch(slot.skel, indices, localMats, objMats, localQuats, outCount);

        for (size_t idx = 0; idx < outCount && outSnap.count < kMaxSyncNodes; ++idx) {
            int bone_local_idx = chain_ref.bones[idx].skelIndex;
            int parent_local_idx =
                (idx == 0) ? chain_ref.parentSkelIndex : chain_ref.bones[idx - 1].skelIndex;
            if (bone_local_idx < 0 || parent_local_idx < 0) continue;
            outSnap.boneIdx[outSnap.count] = bone_local_idx;
            outSnap.parentBoneIdx[outSnap.count] = parent_local_idx;
            outSnap.writeDefault[outSnap.count] = 1;
            outSnap.localMat[outSnap.count] = localMats[idx];
            outSnap.localQuat[outSnap.count] = localQuats[idx];
            outSnap.count++;
        }
    }

    const BlinkProfile* activeBlink =
        FindMatchingBlinkProfile(slot.blinkProfiles, slot.modelHash);
    if (activeBlink != nullptr) {
        float blinkAmt = UpdatePedBlinkAmount(slot, *activeBlink, deltaTime);
        Mat34V blinkLocalMats[kMaxBlinkBonesPerProfile]{};
        Mat34V blinkObjMats[kMaxBlinkBonesPerProfile]{};
        int blinkIndices[kMaxBlinkBonesPerProfile]{};
        int blinkParents[kMaxBlinkBonesPerProfile]{};
        Quat blinkQuats[kMaxBlinkBonesPerProfile]{};
        size_t blinkValid = 0;
        bool anyPosDelta = false;
        Mat34V firstPreLoc{};
        bool hasFirstPreLoc = false;

        for (size_t idx = 0;
             idx < activeBlink->bones.size() &&
             idx < static_cast<size_t>(kMaxBlinkBonesPerProfile);
             ++idx) {
            const BlinkBoneNode& bone_node = activeBlink->bones[idx];
            if (bone_node.skelIndex < 0 ||
                static_cast<uint32_t>(bone_node.skelIndex) >= slot.skel.numBones) {
                continue;
            }
            if (bone_node.parentSkelIndex < 0 ||
                static_cast<uint32_t>(bone_node.parentSkelIndex) >= slot.skel.numBones) {
                continue;
            }

            Mat34V parentObjMtx{};
            bool foundPrev = false;
            for (size_t prev = 0; prev < blinkValid; ++prev) {
                if (blinkIndices[prev] == bone_node.parentSkelIndex) {
                    parentObjMtx = blinkObjMats[prev];
                    foundPrev = true;
                    break;
                }
            }
            if (!foundPrev) {
                if (!SafeReadMat34(
                        reinterpret_cast<uint64_t>(slot.skel.objectMatrices) +
                            static_cast<uint64_t>(bone_node.parentSkelIndex) * sizeof(Mat34V),
                        parentObjMtx) ||
                    !IsValidMat34(parentObjMtx)) {
                    continue;
                }
            }

            if (idx == 0) {
                hasFirstPreLoc = SafeReadMat34(
                    reinterpret_cast<uint64_t>(slot.skel.localMatrices) +
                        static_cast<uint64_t>(bone_node.skelIndex) * sizeof(Mat34V),
                    firstPreLoc);
            }

            Vec3 animatedPos = bone_node.localPos;
            if (VecLen(bone_node.deltaPos) > 1e-6f) {
                animatedPos = VecAdd(bone_node.localPos, VecScale(bone_node.deltaPos, blinkAmt));
                anyPosDelta = true;
            }
            Quat animatedRot = bone_node.localRot;
            float deltaRotVecSq = bone_node.deltaRot.quat_x * bone_node.deltaRot.quat_x +
                                  bone_node.deltaRot.quat_y * bone_node.deltaRot.quat_y +
                                  bone_node.deltaRot.quat_z * bone_node.deltaRot.quat_z;
            if (deltaRotVecSq > 1e-9f || std::fabs(bone_node.deltaRot.quat_w) < 0.999999f) {
                Quat rotOffset = QuatSlerpIdentity(bone_node.deltaRot, blinkAmt);
                animatedRot = QuatMul(bone_node.localRot, rotOffset);
            }
            Mat34V locMat = QuatTransToMat34(animatedRot, animatedPos);
            Mat34V objMat = MulMat34(parentObjMtx, locMat);
            if (!IsValidMat34(locMat) || !IsValidMat34(objMat)) continue;

            blinkIndices[blinkValid] = bone_node.skelIndex;
            blinkParents[blinkValid] = bone_node.parentSkelIndex;
            blinkLocalMats[blinkValid] = locMat;
            blinkObjMats[blinkValid] = objMat;
            blinkQuats[blinkValid] = animatedRot;
            blinkValid++;
        }

        if (blinkValid > 0) {
            SafeWriteSkeletonBatch(
                slot.skel, blinkIndices, blinkLocalMats, blinkObjMats,
                blinkQuats, blinkValid, anyPosDelta);
            for (size_t idx = 0; idx < blinkValid && outSnap.count < kMaxSyncNodes; ++idx) {
                outSnap.boneIdx[outSnap.count] = blinkIndices[idx];
                outSnap.parentBoneIdx[outSnap.count] = blinkParents[idx];
                outSnap.writeDefault[outSnap.count] = anyPosDelta ? 2 : 1;
                outSnap.localMat[outSnap.count] = blinkLocalMats[idx];
                outSnap.localQuat[outSnap.count] = blinkQuats[idx];
                outSnap.count++;
            }

            if (blinkAmt > 0.10f && g_blinkDiagCount < 3) {
                ++g_blinkDiagCount;
                std::ostringstream blink_oss;
                blink_oss << "[Blink] Active ped=0x" << std::hex
                          << reinterpret_cast<uintptr_t>(slot.pedAddr)
                          << " model=0x" << slot.modelHash << std::dec
                          << " amt=" << blinkAmt
                          << " max=" << activeBlink->maxBlink
                          << " valid=" << blinkValid
                          << " bone0=" << blinkIndices[0] << "(parent=" << blinkParents[0] << ")"
                          << " mode=" << (anyPosDelta ? "pos" : "rot");
                if (hasFirstPreLoc) {
                    Quat preRot = Mat34ToQuat(firstPreLoc);
                    blink_oss << " preRot=(" << preRot.quat_x << "," << preRot.quat_y << ","
                              << preRot.quat_z << "," << preRot.quat_w << ")";
                }
                blink_oss << " writtenRot=(" << blinkQuats[0].quat_x << ","
                          << blinkQuats[0].quat_y << "," << blinkQuats[0].quat_z << ","
                          << blinkQuats[0].quat_w << ")";
                WriteLog(blink_oss.str());
            }
        }
    }

    outSnap.active = (outSnap.count > 0);
}

inline void PublishSyncSnapshotList(const SyncSnapshotList& nextList) {
    EnterCriticalSection(&g_syncLock);
    g_syncStateList = nextList;
    LeaveCriticalSection(&g_syncLock);
}

inline void ClearSyncSnapshot() {
    EnterCriticalSection(&g_syncLock);
    g_syncStateList.slotCount = 0;
    LeaveCriticalSection(&g_syncLock);
}

}  // namespace gtav_physbones
