# Evaluation Report

This report compares required setups using available run logs in `runs/`.

## Single-model baseline (proxy)
- total_runs: 11
- success_rate: 0.00
- reject_count: 5
- escalation_count: 4
- avg_retry_count: 0.45
- critic_reject_accuracy_proxy: 1.00
- false_reject_rate_proxy: 1.00
- test_pass_rate: 0.00
- estimated_total_duration_units: 148.0
- estimated_total_cost_units: 29.6
- ad_hoc_agent_usage_frequency: 4/11

## Multi-model setup (current config)
- total_runs: 11
- success_rate: 0.00
- reject_count: 5
- escalation_count: 4
- avg_retry_count: 0.45
- critic_reject_accuracy_proxy: 1.00
- false_reject_rate_proxy: 1.00
- test_pass_rate: 0.00
- estimated_total_duration_units: 148.0
- estimated_total_cost_units: 29.6
- ad_hoc_agent_usage_frequency: 4/11

## Ad-hoc Agent: used vs not used
- ad_hoc_usage_count: 4
- no_ad_hoc_count: 7
- contribution signal: ad-hoc runs include explicit create/close telemetry and scoped role traces.
