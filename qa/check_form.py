#!/usr/bin/env python3
"""Check the form: its own helpers, the payment splits it offers, and real requests.

    python3 qa/check_form.py

Starts build/serve.py on a free local port and sends it the requests the page
sends, built from the sample engagements: a good build, an em dash (replaced), a
leftover token (refused), a bad ABN (refused), a low price (asks first), and a
Sri Lankan app (built as a marked draft); and the example proposal data files.
Also checks the page's script with node
when node is installed. Writes nothing into the project. Exits 1 if anything fails.
"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, f"{ROOT}/build")
import build as builder                                    # noqa: E402
import serve                                               # noqa: E402

VALID_ABN = "51 824 753 556"                               # the ATO's published example ABN
failures = []


def expect(cond, what):
    if not cond:
        failures.append(what)
        print(f"  FAIL     {what}")


def preset(v):
    if isinstance(v, str) and v.startswith("preset:"):
        return json.load(open(f"{ROOT}/presets/{v.split(':', 1)[1]}.json"))
    return v


def form_request(sample, **changes):
    """The JSON the page posts to /build, made from a sample engagement."""
    e = json.load(open(f"{ROOT}/engagements/{sample}.json"))
    listed = builder.SCOPE_LIST[e["engagement_type"]]
    d = {"jurisdiction": e["jurisdiction"], "engagement_type": e["engagement_type"],
         "atp.date": e["atp"]["date"], "atp.ref": e["atp"]["ref"],
         "proposal.ref": e["proposal"]["ref"], "proposal.date": e["proposal"]["date"],
         "scope.inclusions": e["scope"]["inclusions"].split(":", 1)[1],
         "pages": preset(e["scope"][listed]), "scope.platform": e["scope"].get("platform", ""),
         "fee.standard": str(e["fee"]["standard"]), "fee.discount": str(e["fee"]["discount"]),
         "milestones": e["milestones"].split(":", 1)[1],
         "timeline.duration": e["timeline"]["duration"], "tasks": preset(e["timeline"]["tasks"]),
         "support.value": str(e["support"]["included"]["value"]), "support.unit": e["support"]["included"]["unit"],
         "project.name": e["project"]["name"]}
    if "plan" in e["support"]:
        d["support.price"] = str(e["support"]["plan"]["price"])
    if e["scope"].get("devices"):
        d["scope.devices"] = e["scope"]["devices"]
    d.update({f"client.{k}": v for k, v in e["client"].items()})
    if "client.abn" in d:
        d["client.abn"] = VALID_ABN
    d.update(changes)
    return d


def post(port, data):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/build", data=json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(), dict(r.headers)


def contract_text(blob):
    with tempfile.NamedTemporaryFile(suffix=".docx") as fh:
        fh.write(blob); fh.flush()
        with zipfile.ZipFile(fh.name) as z:
            return z.read("word/document.xml").decode("utf-8")


def check_helpers():
    expect(serve.house_dashes("Home — front door") == "Home – front door", "em dash becomes a spaced en dash")
    expect(serve.house_dashes({"a": ["x—y"]}) == {"a": ["x – y"]}, "em dashes replaced inside lists and dicts")
    msgs = serve.final_check_errors("  UNREPLACED TOKENS: ['{{x}}']\n    [a – to confirm]\n")
    expect(len(msgs) == 2 and "curly braces" in msgs[0] and "placeholder" in msgs[1], "final-check messages read clearly")


def check_splits():
    for code, c in serve.country_data().items():
        for t, T in c["types"].items():
            weeks = max(builder.weeks_in(r[-1]) for r in T["plan"])
            expect(T["split"] in T["splits"], f"{code} {t}: the default split is offered")
            for s in T["splits"]:
                expect(not builder.split_week_problems(serve.preset_rows(s), weeks),
                       f"{code} {t}: offered split {s} fits the timeline")
    au = serve.country_data()["AU"]["types"]
    expect("milestones.20-40-40" in au["website"]["splits"] and "milestones.20-40-40" not in au["web_app"]["splits"],
           "20-40-40 is offered for websites and not for apps")


def check_page_script(port):
    if not shutil.which("node"):
        print("  (node not installed: page script not checked)")
        return
    page = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=30).read().decode()
    import re
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write("\n;\n".join(re.findall(r"<script>(.*?)</script>", page, re.S)))
    r = subprocess.run(["node", "--check", fh.name], capture_output=True, text=True)
    os.unlink(fh.name)
    expect(r.returncode == 0, f"the page script parses ({r.stderr.strip()[:120]})")


def check_data_files(port):
    """The example data files fill the form exactly; a .json that is not one is refused."""
    import proposal_data
    au = proposal_data.read(f"{ROOT}/docs/examples/example-au-website.json")["fields"]
    expect(au["milestones"]["value"] == "milestones.20-40-40" and au["timeline.duration"]["value"] == "Eight weeks"
           and au["scope.pages"]["value"][3] == ["Projects", "Recent work, by service", 1]
           and all(v["confidence"] == "high" for k, v in au.items() if k != "atp.ref"),
           "the Australian example data file reads exactly")
    lk = proposal_data.read(f"{ROOT}/docs/examples/example-lk-web-app.json")["fields"]
    expect(lk["jurisdiction"]["value"] == "LK" and lk["milestones"]["value"] == "lk/milestones.20-30-30-20"
           and lk["client.reg_no"]["value"] == "PV00000", "the Sri Lankan example data file reads exactly")

    def upload(name, blob):
        boundary = "qa-boundary"
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
                f"Content-Type: application/json\r\n\r\n").encode() + blob + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(f"http://127.0.0.1:{port}/extract", data=body, method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        return json.loads(urllib.request.urlopen(req, timeout=30).read())

    r = upload("data.json", open(f"{ROOT}/docs/examples/example-au-website.json", "rb").read())
    expect(r.get("fields", {}).get("proposal.ref", {}).get("value") == "26-EXC-WD-070",
           "the form reads an uploaded data file")
    r = upload("other.json", b'{"hello": 1}')
    expect("not a proposal data file" in r.get("error", ""), "a .json that is not a data file is refused")


def check_requests(port):
    body, h = post(port, form_request("sample-example-co"))
    expect(body[:2] == b"PK" and "X-Record" not in h and "X-Draft" not in h,
           "an Australian website builds and downloads, with no record line")

    body, h = post(port, form_request("sample-example-co", **{"project.name": "Example Co — website"}))
    expect(body[:2] == b"PK" and "—" not in contract_text(body) and "Example Co – website" in contract_text(body),
           "an em dash typed into the form becomes an en dash in the contract")

    body, _ = post(port, form_request("sample-example-co", **{"project.name": "{{oops}} site"}))
    expect(body[:1] == b"{" and "curly braces" in body.decode(), "a leftover token is refused, not downloaded")

    body, _ = post(port, form_request("sample-example-co", **{"client.abn": "12 345 678 901"}))
    expect(body[:1] == b"{" and "not a valid ABN" in body.decode(), "a bad ABN is refused")

    body, _ = post(port, form_request("sample-example-co", **{"fee.standard": "450", "fee.discount": "0"}))
    expect(body[:1] == b"{" and '"confirm"' in body.decode(), "a price under $500 asks before building")

    body, h = post(port, form_request("sample-lk-web-app"))
    expect(body[:2] == b"PK" and "X-Draft" in h, "a Sri Lankan web app builds as a marked draft")


def main():
    check_helpers()
    check_splits()
    with socket.socket() as s:                              # a free port
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    env = {**os.environ, "ATP_HOST": "127.0.0.1", "ATP_PORT": str(port), "ATP_OPEN_BROWSER": "0"}
    env.pop("ATP_GITHUB_TOKEN", None)
    server = subprocess.Popen([sys.executable, f"{ROOT}/build/serve.py"], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):                                 # wait for it to listen
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1); break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.2)
        check_page_script(port)
        check_requests(port)
        check_data_files(port)
    finally:
        server.terminate(); server.wait(timeout=10)
    print(f"form: {'all checks pass' if not failures else f'{len(failures)} failed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
