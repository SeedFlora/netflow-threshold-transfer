# P12 publication metadata update

Verified on 5 September 2026.

The earlier related-work files identified only the arXiv precursor, *On the Cross-Dataset Generalization of Machine Learning for Network Intrusion Detection*, arXiv:2402.10974v1 (15 February 2024), and marked the subsequent venue unverified. This was an access limitation of that review, not evidence that no final article existed.

The [current arXiv record](https://arxiv.org/abs/2402.10974) explicitly links DOI `10.1109/ACCESS.2024.3472907` and gives IEEE Access volume 12, pages 144489–144508 (2024). The [Crossref registration](https://api.crossref.org/works/10.1109%2FACCESS.2024.3472907) confirms the same three authors but a changed final title:

> Marco Cantone, Claudio Marrocco, and Alessandro Bria. *Machine Learning in Network Intrusion Detection: A Cross-Dataset Generalization Study*. IEEE Access, vol. 12, pp. 144489–144508, 2024. DOI: 10.1109/ACCESS.2024.3472907.

The raw fetched registration is retained in `P12_publication_update_crossref.json`. Author sequence and final article metadata match the DOI explicitly linked from the precursor. The IEEE document identifier is `10704637`; direct access to its page returned a robot-verification screen during this check. Crossref plus the author-submitted arXiv journal reference establish the publication identity; they do not establish equivalence of every method or result between versions.

## P19 assumption verification performed alongside this update

The actual [ICLR 2024 proceedings PDF](https://proceedings.iclr.cc/paper_files/paper/2024/file/f3549ef9b5ff520a7e41ff3cc306ab2b-Paper-Conference.pdf), Section 2.1, Theorem 1, was inspected. Its core expected-risk guarantee assumes exchangeable random loss functions, each nonincreasing and right-continuous in the control parameter, a finite uniform upper bound, and an achievable risk level at the maximum parameter. The project's empirical pooled/block quantile rules use a different procedure. Their empirical constraints require separate evaluation. The cited paper also develops distribution-shift extensions.
