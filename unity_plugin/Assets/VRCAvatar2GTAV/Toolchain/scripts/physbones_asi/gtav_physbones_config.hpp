#pragma once
/*
 * gtav_physbones_config.hpp
 * =========================
 * Layer 2 (Configuration & Runtime State): Plugin configuration structures,
 * thread-shared sync snapshot descriptors, tracked ped slots, logging helper,
 * and GTAVPhysBones.ini parser supporting per-model scoping and `[Blink_*]`.
 */

#include "gtav_physbones_math.hpp"

#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

namespace gtav_physbones {

// ---------------------------------------------------------------------------
// Configuration & Simulation State Structs
// ---------------------------------------------------------------------------
/** Rest-pose geometry and angular cone constraints for one bone in a chain. */
struct BoneNodeCfg {
    std::string name;
    int tag = 0;
    int skelIndex = -1;
    float maxAngleDeg = 50.0f;
    Vec3 localPos{};
    Quat localRot{0.0f, 0.0f, 0.0f, 1.0f};
    Vec3 limitAxisLocal{0.0f, 1.0f, 0.0f};
};

/** Full VRChat VRCPhysBone chain parameters and live Verlet integration buffers. */
struct PhysBoneChain {
    std::string name;
    std::string model;
    uint32_t modelHash = 0U;
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

/** Rest-pose and closed-eyelid delta transform for one native/custom blink bone. */
struct BlinkBoneNode {
    std::string name;
    int tag = 0;
    int parentTag = 0;
    int skelIndex = -1;
    int parentSkelIndex = -1;
    Vec3 localPos{};
    Quat localRot{0.0f, 0.0f, 0.0f, 1.0f};
    Vec3 deltaPos{};
    Quat deltaRot{0.0f, 0.0f, 0.0f, 1.0f};
};

/** Per-model eye blink timing parameters and bone target list (`[Blink_*]`). */
struct BlinkProfile {
    std::string model = "all";
    uint32_t modelHash = 0;
    bool enabled = true;
    float minInterval = 2.6f;
    float maxInterval = 6.0f;
    float blinkDuration = 0.25f;
    float doubleBlinkChance = 0.18f;
    float maxBlink = 1.0f;
    std::vector<BlinkBoneNode> bones;
};

/** Per-ped eye blink state machine timer and PRNG seed. */
struct BlinkRuntimeState {
    bool initialized = false;
    bool blinking = false;
    bool doubleBlinkPending = false;
    float waitTimer = 0.0f;
    float nextDelay = 2.2f;
    float blinkElapsed = 0.0f;
    uint32_t rngState = 0x9E3779B9U;
};

/** Parsed contents of GTAVPhysBones.ini (general knobs, chains, blink profiles). */
struct PluginConfig {
    bool enabled = true;
    std::string targetPedModel = "player_zero";
    uint32_t targetModelHash = 0;
    float velocityScale = 2.5f;
    float maxDeltaTime = 0.05f;
    std::vector<PhysBoneChain> chains;
    std::vector<BlinkProfile> blinkProfiles;
};

/** Reference bone index + expected rest local position for RAGE skeleton fingerprinting. */
struct ProbeRefBone {
    int skelIndex = -1;
    Vec3 expectedLocalPos{};
};

/** Resolved pointers and structure offsets into a ped's live `rage::crSkeleton`. */
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

/** Lock-free-friendly snapshot applied continuously by the sub-frame sync worker thread. */
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

/** Batch of active sync snapshots across all tracked peds (`<= kMaxTrackedPeds`). */
struct SyncSnapshotList {
    int slotCount = 0;
    SyncSnapshot slots[kMaxTrackedPeds]{};
};

/** Runtime tracking state for one active ped in the game world. */
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

inline PluginConfig g_cfg{};
inline int g_blinkDiagCount = 0;

// ---------------------------------------------------------------------------
// Logging & INI Parsing
// ---------------------------------------------------------------------------
/** Append a diagnostic line to `<ASI dir>\GTAVPhysBones.log`. */
inline void WriteLog(const std::string& line) {
    if (g_baseDir.empty()) return;
    std::ofstream logFile(g_baseDir + "\\GTAVPhysBones.log", std::ios::app);
    if (logFile.is_open()) {
        logFile << line << "\n";
    }
}

inline std::string Trim(const std::string& str_in) {
    size_t start = str_in.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) return "";
    size_t end = str_in.find_last_not_of(" \t\r\n");
    return str_in.substr(start, end - start + 1);
}

inline Vec3 ParseVec3(const std::string& val_str, Vec3 default_vec) {
    std::stringstream stream_in(val_str);
    std::string item;
    float coords[3]{default_vec.coord_x, default_vec.coord_y, default_vec.coord_z};
    int idx = 0;
    while (idx < 3 && std::getline(stream_in, item, ',')) {
        coords[idx++] = static_cast<float>(std::atof(Trim(item).c_str()));
    }
    return {coords[0], coords[1], coords[2]};
}

inline Quat ParseQuat(const std::string& val_str) {
    std::stringstream stream_in(val_str);
    std::string item;
    float coords[4]{0.0f, 0.0f, 0.0f, 1.0f};
    int idx = 0;
    while (idx < 4 && std::getline(stream_in, item, ',')) {
        coords[idx++] = static_cast<float>(std::atof(Trim(item).c_str()));
    }
    return QuatNorm({coords[0], coords[1], coords[2], coords[3]});
}

/**
 * Load and validate `GTAVPhysBones.ini`, precomputing rest segment lengths
 * and JOAAT model hashes for both `[Chain_*]` and `[Blink_*]` sections.
 */
inline bool LoadIniConfig(const std::string& iniPath, PluginConfig& outCfg) {
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
            else if (key == "velocity_scale") {
                outCfg.velocityScale = static_cast<float>(std::atof(val.c_str()));
            } else if (key == "max_delta_time") {
                outCfg.maxDeltaTime = static_cast<float>(std::atof(val.c_str()));
            }
        } else if (activeChainIdx >= 0) {
            PhysBoneChain& chain_ref = outCfg.chains[activeChainIdx];
            if (key == "name") chain_ref.name = val;
            else if (key == "model") chain_ref.model = val;
            else if (key == "parent_bone_tag") chain_ref.parentBoneTag = std::atoi(val.c_str());
            else if (key == "bone_count") {
                int count = std::atoi(val.c_str());
                if (count > 0 && count <= kMaxBonesPerChain) chain_ref.bones.resize(count);
            } else if (key == "integration_type") {
                chain_ref.integrationType = std::atoi(val.c_str());
            } else if (key == "pull") {
                chain_ref.pull = static_cast<float>(std::atof(val.c_str()));
            } else if (key == "spring") {
                chain_ref.spring = static_cast<float>(std::atof(val.c_str()));
            } else if (key == "stiffness") {
                chain_ref.stiffness = static_cast<float>(std::atof(val.c_str()));
            } else if (key == "gravity") {
                chain_ref.gravity = static_cast<float>(std::atof(val.c_str()));
            } else if (key == "gravity_falloff") {
                chain_ref.gravityFalloff = static_cast<float>(std::atof(val.c_str()));
            } else if (key == "immobile") {
                chain_ref.immobile = static_cast<float>(std::atof(val.c_str()));
            } else if (key == "limit_type") {
                chain_ref.limitType = std::atoi(val.c_str());
            } else if (key == "max_angle_x") {
                chain_ref.maxAngleX = static_cast<float>(std::atof(val.c_str()));
            } else if (key == "max_angle_z") {
                chain_ref.maxAngleZ = static_cast<float>(std::atof(val.c_str()));
            } else if (key == "is_animated") {
                chain_ref.isAnimated = std::atoi(val.c_str());
            } else if (key.rfind("bone_", 0) == 0) {
                size_t under = key.find('_', 5);
                if (under != std::string::npos) {
                    int bIdx = std::atoi(key.substr(5, under - 5).c_str());
                    std::string subKey = key.substr(under + 1);
                    if (bIdx >= 0 && bIdx < kMaxBonesPerChain) {
                        if (bIdx >= static_cast<int>(chain_ref.bones.size())) {
                            chain_ref.bones.resize(bIdx + 1);
                        }
                        BoneNodeCfg& bone_node = chain_ref.bones[bIdx];
                        if (subKey == "name") bone_node.name = val;
                        else if (subKey == "tag") bone_node.tag = std::atoi(val.c_str());
                        else if (subKey == "max_angle") {
                            bone_node.maxAngleDeg = static_cast<float>(std::atof(val.c_str()));
                        } else if (subKey == "local_pos") {
                            bone_node.localPos = ParseVec3(val, {0.0f, 0.0f, 0.0f});
                        } else if (subKey == "local_rot") {
                            bone_node.localRot = ParseQuat(val);
                        } else if (subKey == "limit_axis") {
                            bone_node.limitAxisLocal =
                                VecNorm(ParseVec3(val, {0.0f, 1.0f, 0.0f}));
                        }
                    }
                }
            }
        } else if (activeBlinkIdx >= 0) {
            BlinkProfile& blink_prof = outCfg.blinkProfiles[activeBlinkIdx];
            if (key == "model") blink_prof.model = val;
            else if (key == "enabled") blink_prof.enabled = (std::atoi(val.c_str()) != 0);
            else if (key == "min_interval") {
                blink_prof.minInterval = static_cast<float>(std::atof(val.c_str()));
            } else if (key == "max_interval") {
                blink_prof.maxInterval = static_cast<float>(std::atof(val.c_str()));
            } else if (key == "blink_duration") {
                blink_prof.blinkDuration = static_cast<float>(std::atof(val.c_str()));
            } else if (key == "double_blink_chance") {
                blink_prof.doubleBlinkChance = static_cast<float>(std::atof(val.c_str()));
            } else if (key == "max_blink") {
                blink_prof.maxBlink = static_cast<float>(std::atof(val.c_str()));
            } else if (key == "bone_count") {
                int count = std::atoi(val.c_str());
                if (count > 0 && count <= kMaxBlinkBonesPerProfile) blink_prof.bones.resize(count);
            } else if (key.rfind("bone_", 0) == 0) {
                size_t under = key.find('_', 5);
                if (under != std::string::npos) {
                    int bIdx = std::atoi(key.substr(5, under - 5).c_str());
                    std::string subKey = key.substr(under + 1);
                    if (bIdx >= 0 && bIdx < kMaxBlinkBonesPerProfile) {
                        if (bIdx >= static_cast<int>(blink_prof.bones.size())) {
                            blink_prof.bones.resize(bIdx + 1);
                        }
                        BlinkBoneNode& bone_node = blink_prof.bones[bIdx];
                        if (subKey == "name") bone_node.name = val;
                        else if (subKey == "tag") bone_node.tag = std::atoi(val.c_str());
                        else if (subKey == "parent_tag") {
                            bone_node.parentTag = std::atoi(val.c_str());
                        } else if (subKey == "local_pos") {
                            bone_node.localPos = ParseVec3(val, {0.0f, 0.0f, 0.0f});
                        } else if (subKey == "local_rot") {
                            bone_node.localRot = ParseQuat(val);
                        } else if (subKey == "delta_pos") {
                            bone_node.deltaPos = ParseVec3(val, {0.0f, 0.0f, 0.0f});
                        } else if (subKey == "delta_rot") {
                            bone_node.deltaRot = QuatNorm(ParseQuat(val));
                        }
                    }
                }
            }
        }
    }

    outCfg.targetModelHash = JoaatLower(outCfg.targetPedModel);
    for (PhysBoneChain& chain_ref : outCfg.chains) {
        chain_ref.modelHash =
            (chain_ref.model.empty() || chain_ref.model == "all") ? 0U : JoaatLower(chain_ref.model);
        size_t nodeCount = chain_ref.bones.size();
        chain_ref.segLengths.assign(nodeCount > 1 ? nodeCount - 1 : 0, 0.03f);
        for (size_t idx = 0; idx + 1 < nodeCount; ++idx) {
            chain_ref.segLengths[idx] = VecLen(chain_ref.bones[idx + 1].localPos);
        }
        chain_ref.prevPosePos.assign(nodeCount, {0.0f, 0.0f, 0.0f});
        chain_ref.worldPos.assign(nodeCount, {0.0f, 0.0f, 0.0f});
        chain_ref.prevWorldPos.assign(nodeCount, {0.0f, 0.0f, 0.0f});
    }
    for (BlinkProfile& blink_prof : outCfg.blinkProfiles) {
        blink_prof.modelHash = (blink_prof.model.empty() || blink_prof.model == "all")
                                   ? 0U
                                   : JoaatLower(blink_prof.model);
        if (blink_prof.minInterval < 0.4f) blink_prof.minInterval = 0.4f;
        if (blink_prof.maxInterval < blink_prof.minInterval) {
            blink_prof.maxInterval = blink_prof.minInterval + 0.5f;
        }
        if (blink_prof.blinkDuration < 0.08f) blink_prof.blinkDuration = 0.08f;
        if (blink_prof.maxBlink < 0.0f) blink_prof.maxBlink = 0.0f;
        if (blink_prof.maxBlink > 1.5f) blink_prof.maxBlink = 1.5f;
    }
    return !outCfg.chains.empty() || !outCfg.blinkProfiles.empty();
}

}  // namespace gtav_physbones
