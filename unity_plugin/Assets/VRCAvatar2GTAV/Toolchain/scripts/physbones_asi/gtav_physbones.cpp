/*
 * gtav_physbones.cpp
 * ==================
 * Layer 5 (ScriptHookV Entrypoint & Multi-Ped Scheduler): Discovers eligible
 * protagonists, story NPCs, and street pedestrians in the GTA V world,
 * resolves per-ped custom PhysBone / Blink bone indices, hot-reloads
 * `GTAVPhysBones.ini`, drives per-frame physics & blink solving, and publishes
 * snapshots to the sub-frame worker thread.
 *
 * Layered C++ Architecture:
 *   - Layer 1 (`gtav_physbones_math.hpp`):     constants, ScriptHookV API, math
 *   - Layer 2 (`gtav_physbones_config.hpp`):   structs, logging, INI parser
 *   - Layer 3 (`gtav_physbones_skeleton.hpp`): SEH guards, RAGE crSkeleton, sync
 *   - Layer 4 (`gtav_physbones_solver.hpp`):   Verlet + Advanced stiffness & blink
 *   - Layer 5 (`gtav_physbones.cpp`):          world ped scanner & DllMain fiber
 */

#include "gtav_physbones_solver.hpp"

#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

namespace gtav_physbones {

// ---------------------------------------------------------------------------
// Per-Ped Bone Index Resolution & World Candidate Discovery
// ---------------------------------------------------------------------------
/** Resolve skeleton bone indices for all active chains and blink profiles on `ped`. */
bool ResolveChainBoneIndices(
    int ped,
    uint32_t pedModelHash,
    std::vector<PhysBoneChain>& chains,
    std::vector<BlinkProfile>& blinkProfiles,
    ProbeRefBone& outRefA,
    ProbeRefBone& outRefB
) {
    bool changed = false;
    ProbeRefBone nextRefA{};
    ProbeRefBone nextRefB{};
    std::vector<ProbeRefBone> modelRootRefs;
    std::vector<ProbeRefBone> modelAllRefs;
    std::vector<ProbeRefBone> wildcardRootRefs;
    std::vector<ProbeRefBone> wildcardAllRefs;

    for (size_t chain_idx = 0; chain_idx < chains.size(); ++chain_idx) {
        PhysBoneChain& chain_ref = chains[chain_idx];
        int nextParent = CallGetPedBoneIndex(ped, chain_ref.parentBoneTag);
        if (nextParent != chain_ref.parentSkelIndex) {
            changed = true;
            chain_ref.parentSkelIndex = nextParent;
        }
        bool isModelMatch = (pedModelHash != 0U && chain_ref.modelHash == pedModelHash);
        for (size_t node_idx = 0; node_idx < chain_ref.bones.size(); ++node_idx) {
            BoneNodeCfg& bone_node = chain_ref.bones[node_idx];
            int resolved = CallGetPedBoneIndex(ped, bone_node.tag);
            if (resolved < 0 && !bone_node.name.empty()) {
                resolved = CallGetEntityBoneIndexByName(ped, bone_node.name.c_str());
            }
            if (resolved != bone_node.skelIndex) {
                changed = true;
                bone_node.skelIndex = resolved;
            }
            if (resolved >= 0) {
                ProbeRefBone candidate{resolved, bone_node.localPos};
                if (isModelMatch) {
                    if (node_idx == 0) modelRootRefs.push_back(candidate);
                    modelAllRefs.push_back(candidate);
                } else {
                    if (node_idx == 0) wildcardRootRefs.push_back(candidate);
                    wildcardAllRefs.push_back(candidate);
                }
            }
        }
    }

    for (BlinkProfile& blink_prof : blinkProfiles) {
        for (BlinkBoneNode& bone_node : blink_prof.bones) {
            int resolved = CallGetPedBoneIndex(ped, bone_node.tag);
            if (resolved < 0 && !bone_node.name.empty()) {
                resolved = CallGetEntityBoneIndexByName(ped, bone_node.name.c_str());
            }
            int resolvedParent = CallGetPedBoneIndex(ped, bone_node.parentTag);
            if (resolvedParent < 0) {
                if (bone_node.parentTag == 65068) {
                    resolvedParent = CallGetEntityBoneIndexByName(ped, "FACIAL_facialRoot");
                } else {
                    for (const BlinkBoneNode& candidate : blink_prof.bones) {
                        if (candidate.tag == bone_node.parentTag && !candidate.name.empty()) {
                            resolvedParent =
                                CallGetEntityBoneIndexByName(ped, candidate.name.c_str());
                            break;
                        }
                    }
                }
            }
            if (resolved != bone_node.skelIndex || resolvedParent != bone_node.parentSkelIndex) {
                changed = true;
                bone_node.skelIndex = resolved;
                bone_node.parentSkelIndex = resolvedParent;
            }
        }
    }

    const std::vector<ProbeRefBone>& refSource =
        (modelRootRefs.size() >= 2) ? modelRootRefs :
        (modelAllRefs.size() >= 2) ? modelAllRefs :
        (wildcardRootRefs.size() >= 2) ? wildcardRootRefs :
        (!modelAllRefs.empty()) ? modelAllRefs : wildcardAllRefs;
    if (!refSource.empty()) {
        nextRefA = refSource[0];
        for (size_t idx = 1; idx < refSource.size(); ++idx) {
            if (refSource[idx].skelIndex != nextRefA.skelIndex) {
                nextRefB = refSource[idx];
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
    for (const auto& chain_ref : slot.chains) {
        if (chain_ref.parentSkelIndex < 0 || chain_ref.bones.empty() ||
            chain_ref.bones[0].skelIndex < 0) {
            continue;
        }
        ++activeCount;
        oss << " | " << chain_ref.name << " parent=" << chain_ref.parentSkelIndex << " nodes=[";
        for (size_t idx = 0; idx < chain_ref.bones.size(); ++idx) {
            if (idx > 0) oss << ",";
            oss << chain_ref.bones[idx].skelIndex;
        }
        oss << "]";
    }
    oss << " (active=" << activeCount << "/" << slot.chains.size() << ")";
    const BlinkProfile* blink_prof =
        FindMatchingBlinkProfile(slot.blinkProfiles, slot.modelHash);
    if (blink_prof != nullptr) {
        oss << " | Blink(" << blink_prof->model << ",max=" << blink_prof->maxBlink << ") nodes=[";
        for (size_t idx = 0; idx < blink_prof->bones.size(); ++idx) {
            if (idx > 0) oss << ",";
            oss << blink_prof->bones[idx].skelIndex
                << "(p=" << blink_prof->bones[idx].parentSkelIndex << ")";
        }
        oss << "]";
    } else {
        oss << " | Blink=none(profiles=" << slot.blinkProfiles.size() << ")";
    }
    WriteLog(oss.str());
}

/** Check whether `ped` carries at least one configured PhysBone or Blink bone. */
bool HasCustomChainBones(int ped, uint32_t pedModelHash, bool& outHasHead) {
    outHasHead = false;
    if (g_cfg.chains.empty() && g_cfg.blinkProfiles.empty()) return false;
    if (CallGetPedBoneIndex(ped, kSkelHeadTag) < 0) return false;
    outHasHead = true;
    for (const auto& chain_ref : g_cfg.chains) {
        if (chain_ref.modelHash != 0U && chain_ref.modelHash != pedModelHash) continue;
        if (chain_ref.bones.empty()) continue;
        int rootTag = chain_ref.bones[0].tag;
        if (rootTag != 0) {
            if (CallGetPedBoneIndex(ped, rootTag) >= 0) {
                return true;
            }
        } else if (!chain_ref.bones[0].name.empty()) {
            if (CallGetEntityBoneIndexByName(ped, chain_ref.bones[0].name.c_str()) >= 0) {
                return true;
            }
        }
    }
    const BlinkProfile* blink_prof =
        FindMatchingBlinkProfile(g_cfg.blinkProfiles, pedModelHash);
    if (blink_prof != nullptr &&
        (blink_prof->modelHash == pedModelHash || blink_prof->model == "all")) {
        const BlinkBoneNode& bone_node = blink_prof->bones[0];
        if (bone_node.tag != 0 && CallGetPedBoneIndex(ped, bone_node.tag) >= 0) {
            return true;
        }
    }
    return false;
}

/** Check eligibility with per-model negative caching so ambient traffic stays cheap. */
bool IsEligiblePhysBonePed(int ped, bool bypassNegCache, int scanTick, uint32_t& outModelHash) {
    static std::unordered_map<uint32_t, int> s_negModelCooldownTick;
    outModelHash = CallGetEntityModel(ped);
    if (!bypassNegCache && outModelHash != 0) {
        auto cache_iter = s_negModelCooldownTick.find(outModelHash);
        if (cache_iter != s_negModelCooldownTick.end() && scanTick < cache_iter->second) {
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
        for (int idx = 0; idx < count; ++idx) {
            if (outAddrs[idx] == addr) return;
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
        for (int idx = 0; idx < found && count < maxOut; ++idx) {
            tryAdd(worldPeds[idx], false);
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
    for (const auto& chain_ref : slot.chains) {
        if (chain_ref.parentSkelIndex < 0 || chain_ref.bones.empty() ||
            chain_ref.bones[0].skelIndex < 0) {
            continue;
        }
        ++activeCount;
        oss << " | " << chain_ref.name << " parent=" << chain_ref.parentSkelIndex << " nodes=[";
        for (size_t idx = 0; idx < chain_ref.bones.size(); ++idx) {
            if (idx > 0) oss << ",";
            oss << chain_ref.bones[idx].skelIndex;
        }
        oss << "]";
    }
    oss << " (active=" << activeCount << "/" << slot.chains.size() << ")";
    const BlinkProfile* blink_prof =
        FindMatchingBlinkProfile(slot.blinkProfiles, slot.modelHash);
    if (blink_prof != nullptr) {
        oss << " | Blink(" << blink_prof->model << ",max=" << blink_prof->maxBlink << ") nodes=[";
        for (size_t idx = 0; idx < blink_prof->bones.size(); ++idx) {
            if (idx > 0) oss << ",";
            oss << blink_prof->bones[idx].skelIndex
                << "(p=" << blink_prof->bones[idx].parentSkelIndex << ")";
        }
        oss << "]";
    } else {
        oss << " | Blink=none(profiles=" << slot.blinkProfiles.size() << ")";
    }
    WriteLog(oss.str());
}

// ---------------------------------------------------------------------------
// ScriptHookV Fiber Main Loop
// ---------------------------------------------------------------------------
void ScriptMain() {
    std::string iniPath = g_baseDir + "\\GTAVPhysBones.ini";
    if (!LoadIniConfig(iniPath, g_cfg) || !g_cfg.enabled) {
        WriteLog("[WARN] GTAVPhysBones.ini missing or disabled at: " + iniPath);
        return;
    }

    FILETIME lastIniWriteTime{};
    WIN32_FILE_ATTRIBUTE_DATA iniAttr{};
    if (GetFileAttributesExA(iniPath.c_str(), GetFileExInfoStandard, &iniAttr)) {
        lastIniWriteTime = iniAttr.ftLastWriteTime;
    }

    {
        std::ostringstream initOss;
        initOss << "[INIT] GTAVPhysBones loaded ini=" << iniPath
                << " target=" << g_cfg.targetPedModel
                << " hash=0x" << std::hex << g_cfg.targetModelHash
                << std::dec << " chains=" << g_cfg.chains.size()
                << " blinks=" << g_cfg.blinkProfiles.size()
                << " velScale=" << g_cfg.velocityScale
                << " worldScan=" << (g_shv.worldGetAllPeds ? 1 : 0);
        WriteLog(initOss.str());
    }

    std::vector<TrackedPedSlot> slots(kMaxTrackedPeds);
    int iniPollCounter = 0;

    LARGE_INTEGER freq{}, lastTime{}, curTime{};
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&lastTime);

    while (true) {
        g_shv.scriptWait(0);
        if (++iniPollCounter >= 30) {
            iniPollCounter = 0;
            WIN32_FILE_ATTRIBUTE_DATA curAttr{};
            if (GetFileAttributesExA(iniPath.c_str(), GetFileExInfoStandard, &curAttr) &&
                (curAttr.ftLastWriteTime.dwLowDateTime != lastIniWriteTime.dwLowDateTime ||
                 curAttr.ftLastWriteTime.dwHighDateTime != lastIniWriteTime.dwHighDateTime)) {
                PluginConfig nextCfg;
                if (LoadIniConfig(iniPath, nextCfg) && nextCfg.enabled) {
                    lastIniWriteTime = curAttr.ftLastWriteTime;
                    ClearSyncSnapshot();
                    g_cfg = std::move(nextCfg);
                    g_blinkDiagCount = 0;
                    for (auto& slot : slots) {
                        slot = TrackedPedSlot{};
                    }
                    std::ostringstream relOss;
                    relOss << "[INIT] Hot-reloaded ini=" << iniPath
                           << " chains=" << g_cfg.chains.size()
                           << " blinks=" << g_cfg.blinkProfiles.size();
                    WriteLog(relOss.str());
                }
            }
        }
        QueryPerformanceCounter(&curTime);
        float delta_time = static_cast<float>(curTime.QuadPart - lastTime.QuadPart) /
                           static_cast<float>(freq.QuadPart);
        lastTime = curTime;
        bool resetAllChains = false;
        if (delta_time <= 0.0f || delta_time > 0.25f) {
            resetAllChains = true;
            delta_time = 1.0f / 60.0f;
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
        for (int cand_idx = 0; cand_idx < candCount; ++cand_idx) {
            matchedSlotIdx[cand_idx] = -1;
            for (int slot_idx = 0; slot_idx < kMaxTrackedPeds; ++slot_idx) {
                if (slots[slot_idx].occupied && slots[slot_idx].pedAddr == candAddrs[cand_idx]) {
                    slots[slot_idx].pedHandle = candHandles[cand_idx];
                    slots[slot_idx].modelHash = candModels[cand_idx];
                    slots[slot_idx].seenThisFrame = true;
                    if (resetAllChains) {
                        for (auto& chain_ref : slots[slot_idx].chains) {
                            chain_ref.initialized = false;
                        }
                    }
                    matchedSlotIdx[cand_idx] = slot_idx;
                    break;
                }
            }
        }

        for (int cand_idx = 0; cand_idx < candCount; ++cand_idx) {
            if (matchedSlotIdx[cand_idx] >= 0) continue;
            int targetIdx = -1;
            for (int slot_idx = 0; slot_idx < kMaxTrackedPeds; ++slot_idx) {
                if (!slots[slot_idx].occupied) {
                    targetIdx = slot_idx;
                    break;
                }
            }
            if (targetIdx < 0) {
                for (int slot_idx = 0; slot_idx < kMaxTrackedPeds; ++slot_idx) {
                    if (!slots[slot_idx].seenThisFrame) {
                        targetIdx = slot_idx;
                        break;
                    }
                }
            }
            if (targetIdx < 0) continue;

            TrackedPedSlot& slot = slots[targetIdx];
            slot = TrackedPedSlot{};
            slot.occupied = true;
            slot.seenThisFrame = true;
            slot.pedHandle = candHandles[cand_idx];
            slot.pedAddr = candAddrs[cand_idx];
            slot.modelHash = candModels[cand_idx];
            slot.chains.clear();
            for (const PhysBoneChain& cfgChain : g_cfg.chains) {
                if (cfgChain.modelHash == 0U || cfgChain.modelHash == slot.modelHash) {
                    slot.chains.push_back(cfgChain);
                }
            }
            slot.blinkProfiles = g_cfg.blinkProfiles;
            matchedSlotIdx[cand_idx] = targetIdx;
        }

        for (int slot_idx = 0; slot_idx < kMaxTrackedPeds; ++slot_idx) {
            if (slots[slot_idx].occupied && !slots[slot_idx].seenThisFrame) {
                slots[slot_idx] = TrackedPedSlot{};
            }
        }

        static SyncSnapshotList nextSyncList{};
        nextSyncList.slotCount = 0;
        for (int slot_idx = 0; slot_idx < kMaxTrackedPeds; ++slot_idx) {
            nextSyncList.slots[slot_idx].active = false;
            nextSyncList.slots[slot_idx].count = 0;
        }
        for (int slot_idx = 0; slot_idx < kMaxTrackedPeds; ++slot_idx) {
            TrackedPedSlot& slot = slots[slot_idx];
            if (!slot.occupied || !slot.seenThisFrame) continue;

            if (slot.hasSkel) {
                if (ResolveChainBoneIndices(
                        slot.pedHandle, slot.modelHash, slot.chains, slot.blinkProfiles, slot.refA, slot.refB)) {
                    LogBoneIndexChange(slot);
                    slot.hasSkel = false;
                    slot.skel = ResolvedSkeleton{};
                    slot.heavyScanCooldown = 0;
                    for (auto& chain_ref : slot.chains) chain_ref.initialized = false;
                } else if (!IsResolvedSkeletonStillValid(
                               slot.pedHandle, slot.pedAddr, slot.skel, slot.refA, slot.refB)) {
                    slot.hasSkel = false;
                    slot.skel = ResolvedSkeleton{};
                    slot.heavyScanCooldown = 0;
                    for (auto& chain_ref : slot.chains) chain_ref.initialized = false;
                }
            }

            if (!slot.hasSkel) {
                int headIdx = CallGetPedBoneIndex(slot.pedHandle, kSkelHeadTag);
                ResolveChainBoneIndices(
                    slot.pedHandle, slot.modelHash, slot.chains, slot.blinkProfiles, slot.refA, slot.refB);
                bool allowHeavy = (slot.heavyScanCooldown <= 0);
                if (!TryResolvePedSkeleton(
                        slot.pedHandle, headIdx, slot.refA, slot.refB, allowHeavy, slot.skel)) {
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
                for (auto& chain_ref : slot.chains) chain_ref.initialized = false;

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
                UpdatePedChainsAndBuildSync(slot, entMtx, delta_time, outSnap);
                if (outSnap.active) {
                    nextSyncList.slotCount++;
                }
            }
        }

        PublishSyncSnapshotList(nextSyncList);
    }
}

}  // namespace gtav_physbones

// ---------------------------------------------------------------------------
// DLL Lifecycle Entry Point
// ---------------------------------------------------------------------------
BOOL APIENTRY DllMain(HMODULE hInstance, DWORD reason, LPVOID /*reserved*/) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hInstance);
        gtav_physbones::g_selfModule = hInstance;
        char pathBuf[MAX_PATH]{};
        GetModuleFileNameA(hInstance, pathBuf, MAX_PATH);
        std::string fullPath(pathBuf);
        size_t slash = fullPath.find_last_of("\\/");
        gtav_physbones::g_baseDir = (slash != std::string::npos) ? fullPath.substr(0, slash) : ".";

        InitializeCriticalSection(&gtav_physbones::g_syncLock);
        gtav_physbones::g_stopSyncThread = 0;
        gtav_physbones::g_syncThread =
            CreateThread(nullptr, 0, gtav_physbones::SyncThreadProc, nullptr, 0, nullptr);

        if (gtav_physbones::g_shv.Bind()) {
            gtav_physbones::g_shv.scriptRegister(hInstance, gtav_physbones::ScriptMain);
        }
    } else if (reason == DLL_PROCESS_DETACH) {
        InterlockedExchange(&gtav_physbones::g_stopSyncThread, 1);
        if (gtav_physbones::g_syncThread) {
            WaitForSingleObject(gtav_physbones::g_syncThread, 500);
            CloseHandle(gtav_physbones::g_syncThread);
            gtav_physbones::g_syncThread = nullptr;
        }
        DeleteCriticalSection(&gtav_physbones::g_syncLock);
        if (gtav_physbones::g_shv.scriptUnregister) {
            gtav_physbones::g_shv.scriptUnregister(hInstance);
        }
    }
    return TRUE;
}
