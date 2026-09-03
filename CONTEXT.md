# AI Radar

AI Radar is a personal reading system for deciding which AI and ML papers
deserve attention before spending time reproducing or adopting them.

## Language

**Paper brief**:
A compact reading aid generated for each shortlisted paper. It supports triage
and does not claim to replace the full paper.
_Avoid_: Resume, report, full summary

**Deep report**:
An on-demand analysis of one paper's full text, focused on mechanism, evidence,
minimum useful test, infrastructure, risks, and unanswered questions.
_Avoid_: Paper brief, reproduction

**Research page**:
The permanent public page for one paper. It presents the latest paper brief,
editorial status, exposure map, source-linked claims, and available report.
_Avoid_: Deep report, paper URL, dossier

**Editorial status**:
The maturity of a research page: indexed from abstract-level analysis, source
mapped from full text, or independently tested by linked external work.
_Avoid_: Confidence score, verification status

**Source mapped**:
A paper whose full text has been analyzed and whose supporting excerpts are
linked when they can be located. It does not mean human review or reproduction.
_Avoid_: Verified, reviewed, reproduced

**Evidence basis**:
Whether a public finding is source-linked, inferred by AI Radar, or not
evaluated. Source-linked requires a source URL, page, and matching excerpt.
_Avoid_: Confidence score, certainty

**Exposure map**:
A fixed set of adoption concerns shown for every research page, including
quality, compute, operations, compatibility, security, and reproducibility.
_Avoid_: Risk score, readiness score

**Risk note**:
A condition that may negate a claimed gain or make adoption impractical. Its
evidence basis remains visible beside it.
_Avoid_: Warning, failure prediction

**Report request**:
An explicit reader action asking the system to spend model tokens on a deep
report for one paper.
_Avoid_: Automatic report, background summary

**Technical core**:
The formula, algorithm, execution model, or evaluation protocol that most
directly explains what a paper changes. It may explicitly have no formula.
_Avoid_: Mathematics section, technical summary

**Formula walkthrough**:
A source-grounded explanation of one formula, its symbols, its role in the
paper, and any calculation AI Radar derives from it.
_Avoid_: Formula summary, generated formula

**Worked example**:
An illustrative calculation performed by AI Radar from a source formula. It is
not a result measured or claimed by the paper.
_Avoid_: Benchmark, paper result, reproduced result

**Validation tier**:
The smallest infrastructure needed to run a meaningful test of whether the
technique helps the reader's workload.
_Avoid_: Hardware requirement, reproduction tier

**Evidence tier**:
The infrastructure used for the experiment that supports the paper's claim.
It may be much larger than the validation tier.
_Avoid_: Validation tier, minimum hardware

**Infrastructure basis**:
Whether an infrastructure classification is explicit in the paper, inferred
from technical requirements, or unknown.
_Avoid_: Confidence score

**Reproduction**:
An attempt to recreate the paper's reported result under comparable conditions.
AI Radar does not perform reproduction.
_Avoid_: Validation, minimum test
