# Promotion Checklist

Evidence is complete only when every box below is supported by real data from the same frozen run.

- [ ] 2025 H2 holdout has non-zero valid event coverage.
- [ ] 2026 YTD holdout has non-zero valid event coverage through the declared cutoff.
- [ ] All retained events have exact +30m, +60m and +240m outcomes.
- [ ] MAD threshold remains exactly `1.0`.
- [ ] No holdout recalibration or threshold tuning was performed.
- [ ] T0 market execution stress is populated.
- [ ] T5 retest/limit execution stress is populated.
- [ ] 10/30/50 bps scenarios are all evaluated.
- [ ] Same-bar SL/TP ambiguity is fail-closed.
- [ ] Complete SMC historical trade ledger exists.
- [ ] SMC baseline and SMC+macro use identical trade universe and realized-R accounting.
- [ ] Evidence artifacts are hashable and reproducible.
- [ ] Production activation remains `false` until the complete evidence package is reviewed.
