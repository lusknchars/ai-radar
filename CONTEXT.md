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

**Report request**:
An explicit reader action asking the system to spend model tokens on a deep
report for one paper.
_Avoid_: Automatic report, background summary

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
