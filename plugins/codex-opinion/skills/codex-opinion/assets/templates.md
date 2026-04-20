# Context-building templates

Pick one when a user's task intent clearly matches; otherwise compose context without a template. Starting shapes, not forms — adapt, merge, delete, or reorder fields so Codex gets the context this moment needs.

1. **General technical review:** user request; artifact or decision under review; why review is needed; known constraints; evidence; exact question for Codex.
2. **LLM application:** user goal; prompt/model/tool schema; retrieval or memory setup; traces that failed or succeeded; evaluation criteria; safety constraints.
3. **Agentic system:** loop design; tool contracts; state/memory model; stop conditions; logs or traces; failure mode to inspect.
4. **ML training pipeline:** dataset source and splits; target metric; model/config; training logs; validation behavior; suspected bottleneck or risk.
5. **Deep learning model:** architecture or paper reference; tensor shapes; loss/objective; training/inference constraints; benchmarks; code paths to inspect.
6. **Inference or serving:** model/version; endpoint or batch path; latency/cost targets; batching/caching behavior; observed logs; rollout constraints.
7. **MLOps lifecycle:** data/versioning; eval gates; registry and deployment path; monitoring signals; rollback plan; drift or retraining concern.
8. **Data engineering:** sources and schemas; transformation contract; orchestration job; data quality checks; sample failures; lineage or backfill constraints.
9. **Frontend UI:** route/component; intended user behavior; screenshots or browser errors; state/data flow; accessibility constraints; diff or files.
10. **Frontend state/data:** store/hooks/query lifecycle; cache invalidation; API contracts; race conditions; reproduction steps; files to inspect.
11. **Backend API:** endpoint; auth/permissions; request/response examples; database or service dependencies; logs/tests; compatibility constraints.
12. **Database/schema:** current schema; migration diff; data invariants; query or index behavior; rollback needs; production safety concerns.
13. **Unit tests:** target function/module; expected behavior; current tests; missing cases; failures or edge cases; desired assertion level.
14. **Integration or end-to-end tests:** user flow; services involved; fixtures/env; failure output; flake/race clues; coverage gap.
15. **QA or regression:** release scope; changed behavior; acceptance criteria; known risks; manual/automated evidence; blocker threshold.
16. **Performance or load:** workload shape; baseline and target metrics; profiling output; bottleneck hypothesis; infra limits; acceptable trade-offs.
17. **Deployment or infrastructure:** environment; config and secrets model; rollout steps; health checks; logs/alerts; rollback path.
18. **DevSecOps/security:** threat model; auth boundaries; secrets/dependencies/IaC; scan output; blast radius; required mitigations.
19. **Research paper review:** paper/excerpt/link; claim to evaluate; assumptions; relevance to current project; replication or implementation questions.
20. **Paper-to-code implementation:** target result; algorithm details; repo/files; deviations from paper; tests/evals; performance or correctness criteria.
