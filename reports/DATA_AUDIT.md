# Full local dataset audit

Rows: 2,365,424; original columns: 55. ZIP and CSV match expected identity.

Timestamp values retain int64 epoch milliseconds and are interpreted as UTC only for auditing. Original CSV order is not chronological.

The user-provided prior audit inspected descriptive labels. This project does not claim all target labels were previously unseen.

| UTC date | Rows | Attack rows |
|---|---:|---:|
| 2015-01-22 | 1,095,574 | 17,462 |
| 2015-01-23 | 39,778 | 0 |
| 2015-02-18 | 1,230,072 | 110,231 |

Exact record duplicate extras: 14,815; event duplicate extras: 14,815; identical F1 feature vector extras: 230,815.
Conflicting event labels: 0 rows. Exclusions: {'duplicate_event': 14815}.

Sessions: 1,884,756, maximum 1,206 flows. Bidirectional endpoint+port+protocol with start <= running maximum prior end + 60 seconds; heuristic grouping, not true PCAP sessions.

Duplicate events retain their first CSV row; feature-identical flows with different event metadata remain. All rows, including excluded rows, remain in the cache with an integrity reason.

| Column | dtype | Missing | +Inf | -Inf | Constant |
|---|---|---:|---:|---:|---|
| FLOW_START_MILLISECONDS | int64 | 0 | 0 | 0 | False |
| FLOW_END_MILLISECONDS | int64 | 0 | 0 | 0 | False |
| IPV4_SRC_ADDR | <class 'str'> | 0 | 0 | 0 | False |
| L4_SRC_PORT | float64 | 0 | 0 | 0 | False |
| IPV4_DST_ADDR | <class 'str'> | 0 | 0 | 0 | False |
| L4_DST_PORT | float64 | 0 | 0 | 0 | False |
| PROTOCOL | float64 | 0 | 0 | 0 | False |
| L7_PROTO | float64 | 0 | 0 | 0 | False |
| IN_BYTES | float64 | 0 | 0 | 0 | False |
| IN_PKTS | float64 | 0 | 0 | 0 | False |
| OUT_BYTES | float64 | 0 | 0 | 0 | False |
| OUT_PKTS | float64 | 0 | 0 | 0 | False |
| TCP_FLAGS | float64 | 0 | 0 | 0 | False |
| CLIENT_TCP_FLAGS | float64 | 0 | 0 | 0 | False |
| SERVER_TCP_FLAGS | float64 | 0 | 0 | 0 | False |
| FLOW_DURATION_MILLISECONDS | float64 | 0 | 0 | 0 | False |
| DURATION_IN | float64 | 0 | 0 | 0 | False |
| DURATION_OUT | float64 | 0 | 0 | 0 | False |
| MIN_TTL | float64 | 0 | 0 | 0 | False |
| MAX_TTL | float64 | 0 | 0 | 0 | False |
| LONGEST_FLOW_PKT | float64 | 0 | 0 | 0 | False |
| SHORTEST_FLOW_PKT | float64 | 0 | 0 | 0 | False |
| MIN_IP_PKT_LEN | float64 | 0 | 0 | 0 | False |
| MAX_IP_PKT_LEN | float64 | 0 | 0 | 0 | False |
| SRC_TO_DST_SECOND_BYTES | float64 | 63425 | 59068 | 0 | False |
| DST_TO_SRC_SECOND_BYTES | float64 | 0 | 122493 | 0 | False |
| RETRANSMITTED_IN_BYTES | float64 | 0 | 0 | 0 | False |
| RETRANSMITTED_IN_PKTS | float64 | 0 | 0 | 0 | False |
| RETRANSMITTED_OUT_BYTES | float64 | 0 | 0 | 0 | False |
| RETRANSMITTED_OUT_PKTS | float64 | 0 | 0 | 0 | False |
| SRC_TO_DST_AVG_THROUGHPUT | float64 | 0 | 0 | 0 | False |
| DST_TO_SRC_AVG_THROUGHPUT | float64 | 0 | 0 | 0 | False |
| NUM_PKTS_UP_TO_128_BYTES | float64 | 0 | 0 | 0 | False |
| NUM_PKTS_128_TO_256_BYTES | float64 | 0 | 0 | 0 | False |
| NUM_PKTS_256_TO_512_BYTES | float64 | 0 | 0 | 0 | False |
| NUM_PKTS_512_TO_1024_BYTES | float64 | 0 | 0 | 0 | False |
| NUM_PKTS_1024_TO_1514_BYTES | float64 | 0 | 0 | 0 | False |
| TCP_WIN_MAX_IN | float64 | 0 | 0 | 0 | False |
| TCP_WIN_MAX_OUT | float64 | 0 | 0 | 0 | False |
| ICMP_TYPE | float64 | 0 | 0 | 0 | False |
| ICMP_IPV4_TYPE | float64 | 0 | 0 | 0 | False |
| DNS_QUERY_ID | float64 | 0 | 0 | 0 | False |
| DNS_QUERY_TYPE | float64 | 0 | 0 | 0 | False |
| DNS_TTL_ANSWER | float64 | 0 | 0 | 0 | False |
| FTP_COMMAND_RET_CODE | float64 | 0 | 0 | 0 | False |
| SRC_TO_DST_IAT_MIN | float64 | 0 | 0 | 0 | False |
| SRC_TO_DST_IAT_MAX | float64 | 0 | 0 | 0 | False |
| SRC_TO_DST_IAT_AVG | float64 | 0 | 0 | 0 | False |
| SRC_TO_DST_IAT_STDDEV | float64 | 0 | 0 | 0 | False |
| DST_TO_SRC_IAT_MIN | float64 | 0 | 0 | 0 | False |
| DST_TO_SRC_IAT_MAX | float64 | 0 | 0 | 0 | False |
| DST_TO_SRC_IAT_AVG | float64 | 0 | 0 | 0 | False |
| DST_TO_SRC_IAT_STDDEV | float64 | 0 | 0 | 0 | False |
| Label | int64 | 0 | 0 | 0 | False |
| Attack | <class 'str'> | 0 | 0 | 0 | False |

Metadata dependence: labels, IP addresses, absolute timestamps, DNS_QUERY_ID and generated identifiers are excluded by an explicit allowlist. Ports, TTL and TCP windows remain possible environment proxies; optional F2 removes them. No target-based feature selection is used.

All original numeric predictors are cached as float64 for stable chunk schemas, timestamps/row IDs/Label as int64. Model inputs become float32 only inside preprocessing. Parquet uses 100,000-row groups; the directory contains one file for consistent manifest joins.

Full machine-readable details: `reports/dataset_audit.json`; explicit feature order: `reports/feature_schema.json`.
