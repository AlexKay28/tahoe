# Ablation results — GLM-5.3-Flash

| task_id | arm | trials | pass_rate | mean_quality | mean_tokens | p25 | p50 | p75 | mean_wall | tokens/success | RE | RC | RR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| code-fix-01 | classic | 5 | 1.00 | 1.00 | 375.00 | 332.00 | 349.00 | 420.00 | 2.91 | 375.00 | 0.0000 | 0.0000 | 0.0000 |
| code-fix-01 | tahoe | 5 | 1.00 | 1.00 | 314.20 | 254.00 | 277.00 | 365.00 | 1.41 | 314.20 | 0.0000 | 0.0000 | 0.0000 |
| code-fix-02 | classic | 5 | 1.00 | 1.00 | 239.00 | 231.00 | 243.00 | 258.00 | 1.68 | 239.00 | 0.0000 | 0.0000 | 0.0000 |
| code-fix-02 | tahoe | 5 | 1.00 | 1.00 | 180.80 | 170.00 | 177.00 | 182.00 | 0.58 | 180.80 | 0.0000 | 0.0000 | 0.0000 |
| plan-01 | classic | 5 | 1.00 | 1.00 | 704.40 | 625.00 | 719.00 | 726.00 | 4.23 | 704.40 | 0.0000 | 0.0000 | 0.0000 |
| plan-01 | tahoe | 5 | 0.20 | 0.20 | 413.00 | 319.00 | 484.00 | 529.00 | 2.34 | 533.00 | 0.0000 | 0.0000 | 0.0000 |
| recover-01 | classic | 5 | 1.00 | 1.00 | 422.20 | 380.00 | 386.00 | 520.00 | 2.94 | 422.20 | 0.0000 | 0.0000 | 0.0000 |
| recover-01 | tahoe | 5 | 1.00 | 1.00 | 280.60 | 261.00 | 268.00 | 272.00 | 2.68 | 280.60 | 0.0000 | 0.0000 | 0.0000 |
| routing-01 | classic | 5 | 1.00 | 1.00 | 364.60 | 355.00 | 359.00 | 373.00 | 1.88 | 364.60 | 0.0000 | 0.0000 | 0.0000 |
| routing-01 | tahoe | 5 | 1.00 | 1.00 | 272.80 | 259.00 | 263.00 | 294.00 | 1.43 | 272.80 | 0.0000 | 0.0000 | 0.0000 |
| routing-02 | classic | 5 | 0.60 | 0.60 | 1034.60 | 1102.00 | 1111.00 | 1111.00 | 5.63 | 983.67 | 0.0000 | 0.0000 | 0.0000 |
| routing-02 | tahoe | 5 | 1.00 | 1.00 | 561.80 | 525.00 | 574.00 | 580.00 | 2.25 | 561.80 | 0.0000 | 0.0000 | 0.0000 |
| search-01 | classic | 5 | 1.00 | 1.00 | 242.60 | 201.00 | 257.00 | 267.00 | 1.19 | 242.60 | 0.0000 | 0.0000 | 0.0000 |
| search-01 | tahoe | 5 | 1.00 | 1.00 | 218.40 | 217.00 | 228.00 | 232.00 | 0.80 | 218.40 | 0.0000 | 0.0000 | 0.0000 |

| task_id | metric | classic | tahoe |
|---|---|---|---|
| code-fix-01 | pass_rate | 1.00 | 1.00 |
| code-fix-01 | mean_tokens | 375.00 | 314.20 |
| code-fix-01 | p25_tokens | 332.00 | 254.00 |
| code-fix-01 | p75_tokens | 420.00 | 365.00 |
| code-fix-01 | mean_wall | 2.91 | 1.41 |
| code-fix-01 | mean_quality | 1.00 | 1.00 |
| code-fix-01 | tokens_per_success | 375.00 | 314.20 |
| code-fix-01 | re_reasoning_efficiency | 0.00 | 0.00 |
| code-fix-01 | rc_reasoning_concentration | 0.00 | 0.00 |
| code-fix-01 | rr_redundancy_rate | 0.00 | 0.00 |

| task_id | metric | classic | tahoe |
|---|---|---|---|
| code-fix-02 | pass_rate | 1.00 | 1.00 |
| code-fix-02 | mean_tokens | 239.00 | 180.80 |
| code-fix-02 | p25_tokens | 231.00 | 170.00 |
| code-fix-02 | p75_tokens | 258.00 | 182.00 |
| code-fix-02 | mean_wall | 1.68 | 0.58 |
| code-fix-02 | mean_quality | 1.00 | 1.00 |
| code-fix-02 | tokens_per_success | 239.00 | 180.80 |
| code-fix-02 | re_reasoning_efficiency | 0.00 | 0.00 |
| code-fix-02 | rc_reasoning_concentration | 0.00 | 0.00 |
| code-fix-02 | rr_redundancy_rate | 0.00 | 0.00 |

| task_id | metric | classic | tahoe |
|---|---|---|---|
| plan-01 | pass_rate | 1.00 | 0.20 |
| plan-01 | mean_tokens | 704.40 | 413.00 |
| plan-01 | p25_tokens | 625.00 | 319.00 |
| plan-01 | p75_tokens | 726.00 | 529.00 |
| plan-01 | mean_wall | 4.23 | 2.34 |
| plan-01 | mean_quality | 1.00 | 0.20 |
| plan-01 | tokens_per_success | 704.40 | 533.00 |
| plan-01 | re_reasoning_efficiency | 0.00 | 0.00 |
| plan-01 | rc_reasoning_concentration | 0.00 | 0.00 |
| plan-01 | rr_redundancy_rate | 0.00 | 0.00 |

| task_id | metric | classic | tahoe |
|---|---|---|---|
| recover-01 | pass_rate | 1.00 | 1.00 |
| recover-01 | mean_tokens | 422.20 | 280.60 |
| recover-01 | p25_tokens | 380.00 | 261.00 |
| recover-01 | p75_tokens | 520.00 | 272.00 |
| recover-01 | mean_wall | 2.94 | 2.68 |
| recover-01 | mean_quality | 1.00 | 1.00 |
| recover-01 | tokens_per_success | 422.20 | 280.60 |
| recover-01 | re_reasoning_efficiency | 0.00 | 0.00 |
| recover-01 | rc_reasoning_concentration | 0.00 | 0.00 |
| recover-01 | rr_redundancy_rate | 0.00 | 0.00 |

| task_id | metric | classic | tahoe |
|---|---|---|---|
| routing-01 | pass_rate | 1.00 | 1.00 |
| routing-01 | mean_tokens | 364.60 | 272.80 |
| routing-01 | p25_tokens | 355.00 | 259.00 |
| routing-01 | p75_tokens | 373.00 | 294.00 |
| routing-01 | mean_wall | 1.88 | 1.43 |
| routing-01 | mean_quality | 1.00 | 1.00 |
| routing-01 | tokens_per_success | 364.60 | 272.80 |
| routing-01 | re_reasoning_efficiency | 0.00 | 0.00 |
| routing-01 | rc_reasoning_concentration | 0.00 | 0.00 |
| routing-01 | rr_redundancy_rate | 0.00 | 0.00 |

| task_id | metric | classic | tahoe |
|---|---|---|---|
| routing-02 | pass_rate | 0.60 | 1.00 |
| routing-02 | mean_tokens | 1034.60 | 561.80 |
| routing-02 | p25_tokens | 1102.00 | 525.00 |
| routing-02 | p75_tokens | 1111.00 | 580.00 |
| routing-02 | mean_wall | 5.63 | 2.25 |
| routing-02 | mean_quality | 0.60 | 1.00 |
| routing-02 | tokens_per_success | 983.67 | 561.80 |
| routing-02 | re_reasoning_efficiency | 0.00 | 0.00 |
| routing-02 | rc_reasoning_concentration | 0.00 | 0.00 |
| routing-02 | rr_redundancy_rate | 0.00 | 0.00 |

| task_id | metric | classic | tahoe |
|---|---|---|---|
| search-01 | pass_rate | 1.00 | 1.00 |
| search-01 | mean_tokens | 242.60 | 218.40 |
| search-01 | p25_tokens | 201.00 | 217.00 |
| search-01 | p75_tokens | 267.00 | 232.00 |
| search-01 | mean_wall | 1.19 | 0.80 |
| search-01 | mean_quality | 1.00 | 1.00 |
| search-01 | tokens_per_success | 242.60 | 218.40 |
| search-01 | re_reasoning_efficiency | 0.00 | 0.00 |
| search-01 | rc_reasoning_concentration | 0.00 | 0.00 |
| search-01 | rr_redundancy_rate | 0.00 | 0.00 |