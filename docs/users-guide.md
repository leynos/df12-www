# Users' guide

This guide is for readers who need to use Episodic as it exists today:
operators, integrators, and other people who need the supported workflows
without changing the implementation. It covers the user-facing surfaces that
are currently documented in this repository. Maintainer-only build and
extension guidance belongs in the [developers' guide](developers-guide.md).

## 1. Where to start

For any task, begin with the document that matches it:

Example: to verify a fresh checkout, start with
[Getting started](/episodic/docs/getting-started/) and expect the local site to
serve on `http://127.0.0.1:8080/episodic/`.

| Task                                               | Read                                               |
| -------------------------------------------------- | -------------------------------------------------- |
| Bring up a development checkout and verify it runs | [Getting started](/episodic/docs/getting-started/) |
| Understand the HTTP surface                        | [API reference](/episodic/docs/api/)               |
| Prepare source material for intake                 | [Workflow: content](/episodic/workflow/content/)   |
| Review evaluator output and guardrails             | [Workflow: quality](/episodic/workflow/quality/)   |
| Confirm hosting and deployment expectations        | [Hosting](/episodic/hosting/)                      |
| Check delivery progress                            | [Roadmap](/episodic/roadmap/)                      |

The companion site starts at [Episodic](/episodic/). Its available routes are
the overview and [why](/episodic/why/); the
[workflow](/episodic/workflow/), [content](/episodic/workflow/content/), [quality](/episodic/workflow/quality/),
and [audio](/episodic/workflow/audio/) sections; the
[architecture](/episodic/architecture/) and [interfaces](/episodic/interfaces/)
references; the
[documentation](/episodic/docs/), [getting-started](/episodic/docs/getting-started/),
and [API](/episodic/docs/api/) pages; plus the
[roadmap](/episodic/roadmap/), [contributing](/episodic/contributing/), and
[hosting](/episodic/hosting/) pages. The shared
[terms](/episodic/terms-of-use/), [privacy policy](/episodic/privacy-policy/),
and [code of conduct](/episodic/code-of-conduct/) complete the public route set.

### Documentation search

The [documentation](/episodic/docs/) page provides search across the published
Episodic pages and the upstream documentation catalogue. Enter at least two
characters to show matching pages, sections, and upstream documents. The
category listing remains available when JavaScript or the search index is
unavailable.

## 2. Supported behaviour

The current checkout is useful for three things:

1. validating the service in a development environment,
2. exercising the implemented REST surface, and
3. reading the workflow, hosting, and roadmap documents that define the
   current contract.

The [API reference](/episodic/docs/api/) is the best summary of what the
application currently serves. The workflow pages explain the current content
and quality path in the order readers are expected to use it.

## 3. What is not here yet

Do not assume the following are available just because they are designed:

- audio delivery, preview, and export are still roadmap work,
- approval flows are not part of the current contract, and
- the system stops at the draft and evaluation surfaces documented above.

For implementation detail rather than usage guidance, switch to the
[developers' guide](developers-guide.md) or the
[df12 Pages App Design](df12-pages-app-design.md).
