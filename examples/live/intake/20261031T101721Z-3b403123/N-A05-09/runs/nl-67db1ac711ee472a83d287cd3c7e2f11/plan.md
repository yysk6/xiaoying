# 内容活动方案：nl-67db1ac711ee472a83d287cd3c7e2f11

状态：incomplete；backend=deepseek；model=deepseek-v4-pro

字幕功能推广短视频方案最低成本为8单位（素材1+脚本2+基础剪辑4+审核1），超出5单位预算3单位，且预算不可修改，无法在预算内完成该方案。

方案未保存。

## 当前候选与观察

```json
{
  "candidate": {
    "revision": 1,
    "candidate_hash": "05d832ddfe85403cb72c0748aa5e92175faffd050d4e30a72bd9c348e151862b",
    "material_id": "M01",
    "creative_brief": "以\"一键自动字幕，告别手动敲字\"为核心卖点，展示影芽剪辑自动生成字幕并支持文本编辑的便捷体验，突出省时高效，引导用户尝试字幕功能。",
    "production_mode": "basic",
    "script_input_hash": "552094dfed853f449c5ffbbdf47950a0d5ad49d30201ad31421f40b36e0c0e9a"
  },
  "total_units": 8,
  "latest_estimate": {
    "estimate_id": "estimate_700f3c004130b2bd61b3349fc8f635cf17800a21cf07c3f453a7d446f1f0fa49",
    "revision": 1,
    "total_units": 8,
    "total_minutes": 90,
    "feasible": false,
    "budget_gap_units": 3,
    "deadline_gap_minutes": 0
  },
  "missing_fields": [],
  "last_observation": {
    "tool_call_id": "call_00_PnXzwaX3DK4erHYFWwBm5534",
    "tool": "stop_task",
    "ok": true,
    "reused": false,
    "data": {
      "status": "incomplete",
      "reason": "constraints_unsatisfied",
      "message": "字幕功能推广短视频方案最低成本为8单位（素材1+脚本2+基础剪辑4+审核1），超出5单位预算3单位，且预算不可修改，无法在预算内完成该方案。",
      "evaluated_candidates": [
        {
          "estimate_id": "estimate_700f3c004130b2bd61b3349fc8f635cf17800a21cf07c3f453a7d446f1f0fa49",
          "revision": 1,
          "candidate_hash": "05d832ddfe85403cb72c0748aa5e92175faffd050d4e30a72bd9c348e151862b",
          "script_id": "script_552094dfed853f449c5ffbbdf47950a0d5ad49d30201ad31421f40b36e0c0e9a",
          "pricing_hash": "65382bec23e207f48ef1fd7ec59014ce7cd1e9b8f676a2225174f7d621c5e48f",
          "line_items": [
            {
              "step_id": "material_prepare",
              "catalog_item_id": "M01",
              "fee_units": 1,
              "duration_minutes": 10
            },
            {
              "step_id": "script_finalize",
              "catalog_item_id": "script_finalize",
              "fee_units": 2,
              "duration_minutes": 20
            },
            {
              "step_id": "video_edit",
              "catalog_item_id": "video_edit:basic",
              "fee_units": 4,
              "duration_minutes": 45
            },
            {
              "step_id": "review",
              "catalog_item_id": "review",
              "fee_units": 1,
              "duration_minutes": 15
            }
          ],
          "quoted_at": "2026-10-31T10:18:10.639296+00:00",
          "total_units": 8,
          "total_minutes": 90,
          "estimated_finish_at": "2026-10-31T11:48:10.639296+00:00",
          "within_budget": false,
          "within_deadline": true,
          "feasible": false,
          "budget_gap_units": 3,
          "deadline_gap_minutes": 0,
          "alternatives": [
            {
              "total_units": 12,
              "total_minutes": 135,
              "estimated_finish_at": "2026-10-31T12:33:10.639296+00:00",
              "within_budget": false,
              "within_deadline": true,
              "feasible": false,
              "budget_gap_units": 7,
              "deadline_gap_minutes": 0,
              "production_mode": "premium"
            }
          ]
        }
      ],
      "latest_gap": {
        "budget_gap_units": 3,
        "deadline_gap_minutes": 0
      },
      "retained_artifact_ids": [
        "script_552094dfed853f449c5ffbbdf47950a0d5ad49d30201ad31421f40b36e0c0e9a",
        "estimate_700f3c004130b2bd61b3349fc8f635cf17800a21cf07c3f453a7d446f1f0fa49"
      ]
    },
    "error": null
  }
}
```
