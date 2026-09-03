# Users' guide

This guide is for readers who need to use the published sub-sites as they exist
today: operators, integrators, and other people who need the supported
workflows without changing the implementation. It covers the user-facing
surfaces that are currently documented in this repository. Maintainer-only
build and extension guidance belongs in the
[developers' guide](developers-guide.md).

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

## 4. Weaver

Weaver's documentation begins at [/weaver/](/weaver/). Two pages answer most
first questions: [Install](/weaver/install/) for getting the tool, and
[Commands](/weaver/commands/) for what it does once installed.

### 4.1. Navigating the sub-site

The sidebar on the left is the navigation for the whole sub-site. The current
page is highlighted in it, and screen readers announce it as such.

Below 1024 pixels wide there is no room for a sidebar, so it becomes a drawer.
In that layout the sidebar is hidden and a square indigo button — the Weaver
mark — appears at the top left. Pressing it opens the navigation over the page.

The drawer closes four ways, and any of them will do:

- pressing the button again,
- pressing `Escape`,
- clicking or tapping the dimmed area beside the drawer, or
- following any link in it.

While the drawer is open, focus moves into it, so the next `Tab` moves through
the navigation rather than through the page behind it. Closing the drawer
restores focus to wherever it was before the drawer opened; if nothing in
particular held it, focus returns to the button that opened the drawer. The
same fallback applies if whatever held focus has since been removed from the
page or can no longer be focused.

The page behind the drawer does not scroll vertically while it is open, so
dismissing the drawer leaves the page at the same position rather than
somewhere further down. The drawer itself scrolls if the navigation is longer
than the screen.

### 4.2. Copying commands

The install page and the home page show commands with a **Copy** control beside
them. Pressing it puts that command on the clipboard, ready to paste into a
terminal.

There is no on-screen confirmation: the page does not change, and nothing is
announced. Pasting the command is the way to verify that the copy worked. A
browser may also refuse the clipboard on an insecure connection or without
permission, and that refusal is likewise silent.

### 4.3. Current and planned command surface

Weaver still has a prototype surface in the current checkout. These examples
work today:

- `weaver --capabilities`
- `weaver definitions get`
- `weaver act apply-patch`

`act apply-patch` consumes patch content from standard input.

The planned 0.1.0 surface is `weaver <resource> <verb> [FLAGS]`, with `--json`
as the machine switch. Selector-driven commands pass `weaver.selector.v1`
records through `--selectors -`; the daemon is per-user and local, using Unix
sockets by default and loopback-only TCP only for compatibility on non-Unix
systems. Shared mutation guarantees stay the same: parser and
language-server checks where they apply, stale-source refusal, Double-Lock
verification, and idempotent mutations.

Use the current examples until the planned commands ship. `patches apply` and
`symbols rename` remain target wording in the docs, not a promise about the
current binary.

## 5. Netsuke

Netsuke's documentation begins at [/netsuke/docs/](/netsuke/docs/); the home
page is [/netsuke/](/netsuke/).

### 5.1. Navigating the documentation

On screens 1024 pixels wide and up, the documentation and guides pages carry a
sidebar on the left. On a documentation page its entries are grouped under
"Introduction", "Core Concepts", and "Reference"; the current page is
highlighted and announced to screen readers as the current page, and its own
section anchors are listed indented beneath it. A search box sits above the
groups: enter at least two characters to search the documentation, and the
search lists matches to follow.

Below 1024 pixels wide, there is no room for the sidebar. On a documentation
page it is replaced by a bar at the top of the content holding a drop-down of
the documentation pages — choosing one navigates there — and the same search
box.

A guide page's sidebar instead lists that guide's sections under "On this
page" and a short set of "Helpful links", with no search box. Below 1024
pixels wide, a guide has no sidebar or bar; its sections follow in reading
order, and the site-wide navigation bar is the way to other pages.

The site-wide navigation bar has its own menu button below 768 pixels wide.
Pressing it opens the menu; pressing it again, pressing `Escape`, or clicking
outside the menu closes it. This is the same mobile menu shared across the
site.

### 5.2. Breadcrumbs

Every documentation, guide, and example page carries a breadcrumb trail above
its heading, showing the route from the section hub down to that page. The
final entry in the trail is the current page and is marked as such for
assistive technology; earlier entries are links back up the route, except
that an example page's category is shown as plain text.

### 5.3. Example pages

Each example page opens with three labels: the example's category (Basics,
Web, Media, Design, C / C++, or Docs), its level (Beginner or Intermediate),
and "Reviewed syntax", meaning the manifest has been checked against the
shipped example. Two buttons follow the labels: the first usually returns to
the examples hub, and the second points at the most relevant documentation
page. Below the manifest, the transcript of the build runs in a
terminal-styled panel.

For implementation detail rather than usage guidance, switch to the
[developers' guide](developers-guide.md) or the
[df12 Pages App Design](df12-pages-app-design.md).
