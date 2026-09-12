# Exposure review of event-triggered implicit perturbation

Reviewed on 2026-09-12 against [arXiv 2608.21223v1](https://arxiv.org/pdf/2608.21223v1).
The source is the full versioned PDF. Its SHA-256 is recorded in
`content/exposures/2608.21223.json`. Five excerpts were checked against their
recorded PDF pages using whitespace-normalized `pdftotext -raw` output.
This is an editorial source audit, not an executed experiment or a full deep report.

| Area | Source | Decision and scope |
| --- | --- | --- |
| Quality | PDF p. 9, Table I | Report the CIFAR-10 accuracy for PGU-XOR, PGU-Reuse, and Randint. Retain the slightly stronger software reference. The epochs/steps columns measure time to PGU-Reuse's final performance, not time to each method's own final score. |
| Compute | PDF p. 10, section V-D; pp. 11–12, energy comparison | Hardware results use post-layout implementations. The energy comparison covers perturbations and compares simulated IPZO with estimated EPZO energy. It does not provide a GPU bill or total pipeline cost. |
| Latency | PDF p. 11, equation 4 and surrounding text | Report perturbation throughput and its cycle dependence. The no-penalty condition requires the PGU to sustain the IMC array's throughput. Application latency remains unknown. |
| Compatibility | PDF p. 4, section IV-A | The source describes a spiking input, IMC array, and PGU. Paperraft infers that applying the method requires this architecture relationship. Direct GLM/Kimi GPU-server support is not established. |
| Data and training | PDF p. 9, final paragraph | Spikingformer is pretrained on ImageNet-1K and fine-tuned on CIFAR-10 with 75% frozen parameters. SpikeGPT is pretrained on OpenWebText2 and fully fine-tuned and evaluated on WikiText-2/103. |
| Operations | Reviewed architecture and experiments | No supported deployment or rollback assessment. Keep unknown and specify the next operational check. |
| Security | Reviewed source | No supported security assessment. Keep unknown; never treat missing analysis as safety evidence. |
| Reproducibility | Reviewed methods and results | Settings and benchmark descriptions exist. Availability and executability of released design files, seeds, checkpoints, and scripts were not verified. Keep unknown. |

For the user's lower-cost LLM inference workload, this paper does not yet justify
a GPU experiment. The next useful step is to locate runnable artifacts and assess
whether any mechanism transfers to the intended model and hardware. Only then
can an experiment budget be estimated. No model run or GPU rental was performed.

The edition is maintained separately from generated briefs and deep reports.
Publication validates dimension completeness, source version/page relationships,
and required limits. It cannot verify semantic support from metadata alone;
new or revised answers require another source audit. Unknown entries retain no
finding, and a curated review does not promote the page's overall editorial status.
