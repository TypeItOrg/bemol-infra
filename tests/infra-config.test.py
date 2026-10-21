#!/usr/bin/env python3
"""Infrastructure config/script/workflow checks: synthetic envs and mocked Docker.

Uses Python stdlib and the installed docker compose/jq CLIs. Never starts containers,
reads an existing .env, connects via SSH or pushes. Full-stack proof belongs to acceptance.
"""
import argparse
import ast
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

INFRA = Path(__file__).resolve().parents[1]
API = Path(os.environ.get("API_REPO", INFRA.parent / "bemol-api")).resolve()
UI = Path(os.environ.get("UI_REPO", INFRA.parent / "bemol-ui")).resolve()
COMMANDS = []
OLD_SHA = "a" * 40
NEW_SHA = "b" * 40
OTHER_SHA = "c" * 40
CASE_TESTS = {
    "Q01.isolated-compose": ["test_compose_isolation", "test_dokploy_staging_compose", "test_local_acceptance_compose"],
    "Q02.persistent-readiness": ["test_persistent_profile", "test_postgres_final_readiness"],
    "Q03.backup-safety": ["test_backup_safety", "test_acceptance_backup_isolation"],
    "Q04.invalid-input": ["test_invalid_inputs", "test_removed_deployment_commands"],
    "Q04.failed-deploy-request": ["test_dokploy_staging_workflows"],
    "C01.publication-gates": ["test_publication_gates"],
    "C01.existing-flows": ["test_existing_flows", "test_dokploy_staging_workflows"],
    "D01.configuration-runbook": ["test_documented_contract"],
}


def command(args, cwd, env=None, check=True):
    result = subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True)
    COMMANDS.append({"argv": list(map(str, args)), "cwd": str(cwd),
                     "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
    if check and result.returncode:
        raise AssertionError(f"{args!r} failed ({result.returncode}): {result.stderr}")
    return result


def synthetic_env():
    return {
        "UI_VERSION": "sha-" + OLD_SHA, "API_VERSION": "sha-" + OTHER_SHA,
        "AUTH_COOKIE_SECURE": "true", "DB_NAME": "disposable", "DB_USER": "disposable",
        "DB_PASSWORD": "synthetic-only", "JWT_SECRET": "synthetic-only-key-" + "x" * 32,
        "REFRESH_REPLAY_ENCRYPTION_KEY": "c3ludGhldGljLW9ubHktMzItYnl0ZS1rZXktMDAwMDA=",
        "WEBAUTHN_RP_ID": "acceptance.example.invalid", "WEBAUTHN_ALLOWED_ORIGINS": "https://acceptance.example.invalid",
        "MAIL_HOST": "external.invalid", "MAIL_USERNAME": "synthetic-unused", "MAIL_PASSWORD": "synthetic-unused",
        "MAIL_FROM": "fixture@example.invalid", "PASSWORD_RECOVERY_FRONTEND_URL": "https://acceptance.example.invalid",
    }


def write_env(path, values):
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    path.chmod(0o600)


def cli_environment():
    # Compose interpolation must not inherit any developer environment variable.
    return {k: v for k, v in os.environ.items() if k in
            {"PATH", "HOME", "DOCKER_HOST", "DOCKER_CONFIG", "XDG_RUNTIME_DIR"}}


def job(text, name):
    match = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [\w-]+:\n|\Z)", text, re.M | re.S)
    if not match:
        raise AssertionError(f"Missing job {name}")
    return match.group(0)


def scalar(text, indent, key):
    match = re.search(rf"^{' ' * indent}{re.escape(key)}: ([^\n]+)$", text, re.M)
    if not match:
        raise AssertionError(f"Missing scalar {key}")
    value = match.group(1)
    if value in (">-", ">", "|"):
        lines = text[match.end():].splitlines()
        # Restrict multiline condition to contiguous indentation, not later steps.
        value_lines = []
        for line in lines[1:]:
            if not line.startswith(" " * (indent + 2)):
                break
            value_lines.append(line.strip())
        value = " ".join(value_lines)
    return value


def condition(text, event, ref):
    expression = scalar(text, 4, "if")
    expression = expression.replace("github.event_name", repr(event)).replace("github.ref_name", repr(ref))
    expression = expression.replace("&&", " and ").replace("||", " or ")
    tree = ast.parse(expression, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.Compare, ast.Eq, ast.Constant)):
            raise AssertionError(f"Unsupported CI condition: {expression}")
    return eval(compile(tree, "<ci-condition>", "eval"), {"__builtins__": {}}, {})


def run_block(workflow, step):
    match = re.search(rf"^      - name: {re.escape(step)}\n(.*?)(?=^      - name:|\Z)", workflow, re.M | re.S)
    if not match:
        raise AssertionError(f"Missing step {step}")
    block = re.search(r"^        run: \|\n((?:          [^\n]*\n|\n)+)", match.group(1), re.M)
    if not block:
        raise AssertionError(f"Missing executable body in {step}")
    return "\n".join(line[10:] for line in block.group(1).splitlines())


class InfraConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="bemol-infra-config-")
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)

    def render(self, values):
        env_file = self.work / "synthetic-staging.env"
        write_env(env_file, values)
        result = command(["docker", "compose", "--env-file", str(env_file),
                          "-f", str(INFRA / "compose.dokploy.staging.yaml"),
                          "config", "--format", "json"], INFRA, cli_environment())
        return json.loads(result.stdout)

    def test_compose_isolation(self):
        spec = importlib.util.spec_from_file_location("acceptance_runtime", INFRA / "scripts/verification/runtime.py")
        runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runtime)
        state = {"namespace": "bemol-acceptance-synthetic", "owner": "synthetic-owner", "tlsPort": 8443,
                 "images": {"api": {"tag": "synthetic-api:local"}, "ui": {"tag": "synthetic-ui:local"}}, "stacks": {}}
        configs = []
        for key in ("qa", "staging"):
            runtime.make_stack(state, key, f"{key}.example.invalid", self.work)
            stack = state["stacks"][key]
            result = command(["docker", "compose", "--profile", "maintenance", "--env-file", stack["envFile"],
                              "-f", str(INFRA / "compose.yaml"), "-f", stack["overrideFile"],
                              "config", "--format", "json"], INFRA, cli_environment())
            configured = json.loads(result.stdout)
            configs.append(configured)
            services = configured["services"]
            for service in ("postgres", "redis"):
                self.assertNotIn("ports", services[service])
            self.assertEqual(services["postgres"]["image"], "postgres:18-alpine")
            self.assertIn("readiness", " ".join(services["api"]["healthcheck"]["test"]))
            self.assertIn("pg_isready", " ".join(services["postgres"]["healthcheck"]["test"]))
            helper = services["api-storage-init"]
            self.assertEqual(helper["image"], services["api"]["image"])
            self.assertEqual(helper["network_mode"], "none")
            self.assertEqual([v["source"] for v in helper["volumes"]], ["api-storage"])
        left, right = configs
        self.assertTrue({v["name"] for v in left["volumes"].values()}.isdisjoint(
            v["name"] for v in right["volumes"].values()))
        self.assertNotEqual(left["networks"]["default"]["name"], right["networks"]["default"]["name"])
        live = self.render(synthetic_env())
        for fixture in configs:
            self.assertTrue({v["name"] for v in fixture["volumes"].values()}.isdisjoint(
                v["name"] for v in live["volumes"].values()))
            self.assertNotEqual(fixture["networks"]["default"]["name"], live["networks"]["default"]["name"])

    def test_dokploy_staging_compose(self):
        compose_file = INFRA / "compose.dokploy.staging.yaml"
        self.assertNotRegex(compose_file.read_text(), r"(?m)^[^#\n]*!(?:reset|override)\b")
        env_file = self.work / "synthetic-dokploy.env"
        write_env(env_file, synthetic_env() | {"UI_VERSION": "staging", "API_VERSION": "staging"})
        result = command(["docker", "compose", "--env-file", str(env_file), "-f",
                          str(compose_file), "config", "--format", "json"],
                         INFRA, cli_environment())
        configured = json.loads(result.stdout)
        expected_volumes = {
            "ui-next-cache": "bemol-ui-next-cache-staging",
            "postgres-data": "bemol-api-postgres-data-staging",
            "redis-data": "bemol-api-redis-data-staging",
            "api-logs": "bemol-api-logs-staging",
            "api-storage": "bemol-api-enrollment-storage-staging",
        }
        self.assertEqual(configured["volumes"], {key: {"external": True, "name": name}
                                                 for key, name in expected_volumes.items()})
        services = configured["services"]
        self.assertEqual(services["postgres"]["environment"]["DB_REQUIRE_EXISTING"], "true")
        self.assertEqual(set(services), {"ui", "api", "postgres", "redis", "api-storage-init"})
        self.assertNotIn("ports", services["ui"])
        api_ports = services["api"]["ports"]
        self.assertEqual([(port["host_ip"], int(port["published"]), port["target"]) for port in api_ports],
                         [("127.0.0.1", 8080, 8080)])
        for name, service in services.items():
            self.assertNotIn("container_name", service)
            if name in ("postgres", "redis"):
                self.assertNotIn("ports", service)
            self.assertEqual("dokploy-network" in service.get("networks", {}), name == "ui")
        self.assertEqual(set(services["ui"]["networks"]), {"default", "dokploy-network"})
        self.assertEqual(configured["networks"]["default"]["name"], "bemol-network-staging")
        self.assertTrue(configured["networks"]["default"]["external"])
        self.assertTrue(configured["networks"]["dokploy-network"]["external"])
        self.assertEqual(services["api"]["depends_on"]["api-storage-init"]["condition"],
                         "service_completed_successfully")
        helper = services["api-storage-init"]
        self.assertFalse(helper.get("profiles"))
        self.assertEqual(helper["network_mode"], "none")
        self.assertEqual(helper["image"], services["api"]["image"])
        for name in ("ui", "api", "api-storage-init"):
            self.assertEqual(services[name]["pull_policy"], "always")
            self.assertTrue(services[name]["image"].endswith(":staging"))
        mounts = services["postgres"]["volumes"]
        wrapper = next(mount for mount in mounts if mount["target"] == "/usr/local/bin/postgres-entrypoint.sh")
        self.assertEqual(wrapper["source"], str(INFRA.parent / "files/postgres-entrypoint.sh"))
        self.assertEqual(wrapper["type"], "bind")
        self.assertTrue(wrapper["read_only"])
        self.assertFalse(wrapper["bind"]["create_host_path"])
        data = next(mount for mount in mounts if mount["target"] == "/var/lib/postgresql")
        self.assertEqual((data["type"], data["source"]), ("volume", "postgres-data"))

    def test_local_acceptance_compose(self):
        spec = importlib.util.spec_from_file_location("acceptance_runtime", INFRA / "scripts/verification/runtime.py")
        runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runtime)
        state = {"namespace": "bemol-acceptance-synthetic", "owner": "synthetic-owner", "tlsPort": 8443,
                 "images": {"api": {"tag": "synthetic-api:local"}, "ui": {"tag": "synthetic-ui:local"}}, "stacks": {}}
        runtime.make_stack(state, "qa", "testing.typeit.com.ar", self.work)
        stack = state["stacks"]["qa"]
        result = command(["docker", "compose", "--profile", "maintenance", "--env-file", stack["envFile"],
                          "-f", str(INFRA / "compose.yaml"), "-f", stack["overrideFile"], "config", "--format", "json"],
                         INFRA, cli_environment())
        configured = json.loads(result.stdout)
        api = configured["services"]["api"]
        self.assertEqual(api["environment"]["SPRING_PROFILES_ACTIVE"], "prod")
        self.assertEqual(api["environment"]["MAIL_HOST"], "mailpit")
        self.assertEqual(api["environment"]["MAIL_SMTP_AUTH"], "false")
        self.assertEqual(api["depends_on"]["mailpit"]["condition"], "service_healthy")
        self.assertEqual(configured["services"]["mailpit"]["image"], "axllent/mailpit:v1.31.3")
        self.assertEqual(configured["services"]["mailpit"]["healthcheck"]["test"], ["CMD", "/mailpit", "readyz"])
        self.assertEqual(api["image"], "synthetic-api:local")
        for volume in configured["volumes"].values():
            self.assertFalse(volume.get("external", False))
            self.assertTrue(volume["name"].startswith(state["namespace"] + "-"))

    def test_persistent_profile(self):
        values = {}
        for name in ("application.properties", "application-prod.properties"):
            values.update(line.split("=", 1) for line in (API / "src/main/resources" / name).read_text().splitlines()
                          if line and not line.startswith("#") and "=" in line)
        self.assertEqual(values["spring.jpa.hibernate.ddl-auto"], "validate")
        self.assertEqual(values["spring.flyway.locations"], "classpath:db/migration")
        self.assertEqual(values["spring.datasource.driver-class-name"], "org.postgresql.Driver")
        self.assertTrue(values["spring.datasource.url"].startswith("jdbc:postgresql:"))
        self.assertEqual(values["spring.sql.init.mode"], "never")
        self.assertEqual(values["springdoc.api-docs.enabled"], "false")
        self.assertEqual(values["springdoc.swagger-ui.enabled"], "false")
        guard = API / "src/main/java/ar/edu/utn/frvm/typeit/bemol_api/auth/config/WebAuthnDeploymentGuard.java"
        exemptions = re.findall(r'profile.equalsIgnoreCase\("([^"]+)"\)', guard.read_text())
        self.assertEqual(set(exemptions), {"dev", "test"})

    def test_postgres_final_readiness(self):
        bindir = self.work / "bin"
        bindir.mkdir()
        # initdb's temporary server accepts Unix sockets immediately; the real TCP
        # endpoint becomes ready only on the third probe. CREATE must never run early.
        implementations = {
            "docker-entrypoint.sh": '''#!/usr/bin/env python3
import os,pathlib,time
work=pathlib.Path(os.environ['PG_TEST_WORK'])
deadline=time.monotonic()+5
while not (work/'created').exists():
    if time.monotonic()>deadline: raise SystemExit(9)
    time.sleep(.01)
''',
            "pg_isready": '''#!/usr/bin/env python3
import json,os,pathlib,sys
work=pathlib.Path(os.environ['PG_TEST_WORK'])
with (work/'probes.jsonl').open('a') as stream: stream.write(json.dumps(sys.argv[1:])+'\\n')
if '-h' not in sys.argv: raise SystemExit(0)
if sys.argv[sys.argv.index('-h')+1]!='127.0.0.1': raise SystemExit(8)
count_file=work/'probe-count'
count=int(count_file.read_text())+1 if count_file.exists() else 1
count_file.write_text(str(count))
if count<3: raise SystemExit(1)
(work/'tcp-ready').touch()
''',
            "psql": '''#!/usr/bin/env python3
import os,pathlib,sys
work=pathlib.Path(os.environ['PG_TEST_WORK'])
if not (work/'tcp-ready').exists(): raise SystemExit(10)
if any('CREATE DATABASE' in arg for arg in sys.argv): (work/'created').touch()
''',
            "sleep": "#!/bin/sh\nexit 0\n",
        }
        for name, source in implementations.items():
            target = bindir / name
            target.write_text(source)
            target.chmod(0o755)
        environment = cli_environment() | {"PATH": str(bindir)+":"+os.environ["PATH"],
                                            "PG_TEST_WORK": str(self.work), "POSTGRES_USER": "fixture", "DB_NAME": "fixture_db"}
        command(["sh", str(INFRA / "docker/postgres-entrypoint.sh")], self.work, environment)
        probes = [json.loads(line) for line in (self.work / "probes.jsonl").read_text().splitlines()]
        self.assertEqual(len(probes), 3)
        self.assertTrue(all(probe[probe.index("-h")+1] == "127.0.0.1" for probe in probes))
        self.assertTrue((self.work / "created").exists())

    def test_invalid_inputs(self):
        shutil.copy2(INFRA / "Makefile", self.work / "Makefile")
        for environment in ("production", "bad", "../staging", "%", "staging production", "qa", ""):
            result = command(["make", "--no-print-directory", "help", "ENV=" + environment],
                             self.work, cli_environment(), False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ENV must be staging", result.stderr)

    def test_removed_deployment_commands(self):
        shutil.copy2(INFRA / "Makefile", self.work / "Makefile")
        for target in ("prepare", "preflight", "bootstrap", "deploy-api", "deploy-ui",
                       "rollback-api", "rollback-ui", "status", "logs", "logs-api",
                       "logs-api-file", "logs-api-request", "down"):
            result = command(["make", "-n", target, "ENV=staging"], self.work, cli_environment(), False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No rule to make target", result.stderr)
        backup = command(["make", "-n", "backup-db", "ENV=staging"], INFRA, cli_environment())
        self.assertIn("flock /tmp/bemol-infra-staging.lock ./scripts/backup-postgres.sh staging", backup.stdout)

    def test_backup_safety(self):
        command(["sh", str(INFRA / "tests/backup-postgres.test.sh")], INFRA, cli_environment())

    def test_acceptance_backup_isolation(self):
        spec = importlib.util.spec_from_file_location("acceptance_runtime", INFRA / "scripts/verification/runtime.py")
        runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runtime)
        state = {"privateDir": str(self.work), "stacks": {"qa": {
            "volumes": {"postgres-data": "bemol-acceptance-owned-postgres"},
            "containers": {"postgres": "fixture-postgres"}}}}
        checks = []
        def owned(*args):
            checks.append(args[1:])
        def run(args, **kwargs):
            self.assertEqual(checks, [("volume", "bemol-acceptance-owned-postgres"),
                                      ("container", "fixture-postgres")])
            self.assertIn("BACKUP_POSTGRES_VOLUME=bemol-acceptance-owned-postgres", args)
            self.assertIn(f"BACKUP_DIR={self.work / 'backups'}", args)
            self.assertNotIn("bemol-api-postgres-data-staging", " ".join(map(str, args)))
            raise RuntimeError("synthetic stop before Docker")
        with mock.patch.object(runtime, "owned", side_effect=owned), mock.patch.object(runtime, "run", side_effect=run):
            with self.assertRaisesRegex(RuntimeError, "synthetic stop before Docker"):
                runtime.check_backup(state, {})

    def test_publication_gates(self):
        for repo in (API, UI):
            ci = (repo / ".github/workflows/ci.yaml").read_text()
            deploy = (repo / ".github/workflows/deploy-staging.yaml").read_text()
            self.assertIn("  workflow_call:\n", ci)
            self.assertIn("  push:\n    branches:\n      - develop\n      - main\n", ci)
            self.assertIn("  pull_request:\n    branches:\n      - develop\n      - staging\n      - main\n", ci)
            self.assertIn("on:\n  push:\n    branches:\n      - staging\n", deploy)
            self.assertNotIn("workflow_dispatch", deploy)
            self.assertNotIn("workflow_run", deploy)
            self.assertEqual(scalar(job(deploy, "ci"), 4, "uses"), "./.github/workflows/ci.yaml")
            self.assertNotIn("secrets: inherit", deploy)
            for forbidden in ("publish-image:", "deploy-staging:", "packages: write", "DOKPLOY_"):
                self.assertNotIn(forbidden, ci)
            publish = job(deploy, "publish-image")
            self.assertEqual(scalar(publish, 4, "needs"), "ci")
            for event in ("push", "pull_request", "workflow_dispatch", "workflow_run"):
                for ref in ("develop", "staging", "main", "feature/example"):
                    self.assertEqual(condition(publish, event, ref), event == "push" and ref == "staging")
            self.assertIn("ref: ${{ github.sha }}", publish)
            self.assertIn("sha-${{ github.sha }}", publish)
            self.assertIn("push: true", publish)
            for workflow in (ci, deploy):
                self.assertNotIn("ubuntu-latest", workflow)
                self.assertNotIn("actions/upload-artifact@v4", workflow)
                for runner in re.findall(r"runs-on: (.+)", workflow):
                    self.assertEqual(runner, "ubuntu-24.04")
            if repo == API:
                self.assertIn("staticAnalysis", job(ci, "static-analysis"))
                self.assertIn("spotlessCheck fastTest", job(ci, "test"))
                self.assertIn("integrationTest", job(ci, "test"))
                self.assertIn("spotlessCheck test", job(ci, "test"))
                self.assertEqual(ci.count("uses: actions/cache@v5"), 2)
                self.assertEqual(ci.count("key: gradle-${{ runner.os }}-${{ runner.arch }}-${{ github.job }}-${{ github.sha }}"), 2)
                self.assertEqual(ci.count("restore-keys: gradle-${{ runner.os }}-${{ runner.arch }}-${{ github.job }}-"), 2)
                self.assertNotIn("gradle/actions/setup-gradle", ci)
                self.assertNotIn("cache: gradle", ci)
                self.assertIn("--build-cache", ci)
                self.assertIn("--profile", ci)
                self.assertIn("build/test-results/", ci)
                self.assertIn("outputs.cacheIf { false }", (repo / "build.gradle").read_text())
            else:
                for gate in ("format:check", "lint", "typecheck", "test --runInBand", "build"):
                    self.assertIn("run: pnpm " + gate, job(ci, "verify"))

    def test_existing_flows(self):
        for repo in (API, UI):
            workflows = repo / ".github/workflows"
            workflow = (workflows / "ci.yaml").read_text()
            deploy = (workflows / "deploy-staging.yaml").read_text()
            self.assertEqual(scalar(workflow, 0, "name"), "CI")
            self.assertEqual(scalar(deploy, 0, "name"), "Deploy staging")
            for removed in ("ci-staging.yaml", "deploy-qa.yaml", "deploy-production.yaml"):
                self.assertFalse((workflows / removed).exists(), removed)
        values = synthetic_env() | {
            "AUTO_LOGIN_ENABLED": "true",
            "AUTO_LOGIN_USER_ID": "00000000-0000-0000-0000-000000000001",
            "AUTO_LOGIN_INSTITUTION_ID": "00000000-0000-0000-0000-000000000002",
        }
        rendered = self.render(values)
        self.assertEqual(rendered["services"]["api"]["environment"]["SPRING_PROFILES_ACTIVE"], "staging")
        for service in ("ui", "api"):
            keys = ("AUTO_LOGIN_ENABLED",) if service == "ui" else tuple(k for k in values if k.startswith("AUTO_LOGIN_"))
            for key in keys:
                self.assertEqual(rendered["services"][service]["environment"][key], values[key])

    def test_dokploy_staging_workflows(self):
        bindir = self.work / "workflow-bin"
        bindir.mkdir()
        request = self.work / "dokploy-request.json"
        curl = bindir / "curl"
        curl.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
pathlib.Path(os.environ['DOKPLOY_TRACE']).write_text(json.dumps(sys.argv[1:]))
sys.exit(int(os.environ.get('CURL_EXIT', '0')))
''')
        curl.chmod(0o755)
        values = {"DOKPLOY_URL": "https://deploy.example.invalid/", "DOKPLOY_API_KEY": "synthetic-api-key",
                  "DOKPLOY_STAGING_COMPOSE_ID": 'compose "quoted" \\ $(touch injected)'}
        environment = cli_environment() | values | {"PATH": str(bindir) + ":" + os.environ["PATH"],
                                                    "DOKPLOY_TRACE": str(request), "GITHUB_SHA": NEW_SHA,
                                                    "GITHUB_REPOSITORY": "typeitorg/bemol-synthetic"}
        for repo in (API, UI):
            workflow = (repo / ".github/workflows/deploy-staging.yaml").read_text()
            deploy = job(workflow, "deploy-staging")
            self.assertEqual(scalar(deploy, 4, "needs"), "publish-image")
            self.assertEqual(scalar(deploy, 4, "environment"), "staging")
            for event in ("push", "pull_request", "workflow_dispatch"):
                for ref in ("develop", "staging", "main"):
                    self.assertEqual(condition(deploy, event, ref), event == "push" and ref == "staging")
            for key in values:
                self.assertIn(f"{key}: ${{{{ secrets.{key} }}}}", deploy)
            for forbidden in ("ssh", "git pull", "make deploy", "API_VERSION", "UI_VERSION", "freshVolumes"):
                self.assertNotIn(forbidden, deploy)
            body = run_block(workflow, "Request staging deployment")
            self.assertIn("--proto '=https'", body)
            result = command(["bash", "-e", "-o", "pipefail", "-c", body], self.work, environment)
            args = json.loads(request.read_text())
            self.assertIn("https://deploy.example.invalid/api/compose.deploy", args)
            for flag in ("--fail", "--silent", "--show-error"):
                self.assertIn(flag, args)
            self.assertEqual(args[args.index("--request") + 1], "POST")
            self.assertIn("x-api-key: " + values["DOKPLOY_API_KEY"], args)
            self.assertIn("Content-Type: application/json", args)
            self.assertEqual(json.loads(args[args.index("--data") + 1]),
                             {"composeId": values["DOKPLOY_STAGING_COMPOSE_ID"],
                              "title": "typeitorg/bemol-synthetic@" + NEW_SHA})
            self.assertNotIn(values["DOKPLOY_API_KEY"], result.stdout + result.stderr)
            self.assertFalse((self.work / "injected").exists())
            for missing in values:
                request.unlink(missing_ok=True)
                rejected = command(["bash", "-e", "-o", "pipefail", "-c", body], self.work,
                                   environment | {missing: ""}, False)
                self.assertNotEqual(rejected.returncode, 0)
                self.assertFalse(request.exists())
            failed = command(["bash", "-e", "-o", "pipefail", "-c", body], self.work,
                             environment | {"CURL_EXIT": "22"}, False)
            self.assertEqual(failed.returncode, 22)

    def test_documented_contract(self):
        template = (INFRA / ".env.dokploy.staging.example").read_text()
        values = dict(line.split("=", 1) for line in template.splitlines() if line and not line.startswith("#"))
        self.assertEqual(values["INSTITUTIONAL_BASE_DOMAIN"], "staging.typeit.com.ar")
        self.assertEqual(values["WEBAUTHN_RP_ID"], "staging.typeit.com.ar")
        self.assertEqual(values["WEBAUTHN_ALLOWED_ORIGINS"], "https://staging.typeit.com.ar")
        for key in ("DB_PASSWORD", "JWT_SECRET", "REFRESH_REPLAY_ENCRYPTION_KEY"):
            self.assertIn(key, values)
        self.assertIn("Dokploy", (INFRA / "docs/DOKPLOY-STAGING.md").read_text())
        for removed in ("compose.staging.yaml", "compose.production.yaml", ".env.example",
                        "docs/STAGING.md", "docs/PRODUCTION.md", "deploy/nginx",
                        "scripts/bootstrap.sh", "scripts/prepare-volumes.sh", "scripts/deploy-service.sh",
                        "scripts/rollback-service.sh"):
            self.assertFalse((INFRA / removed).exists(), removed)
        command(["sh", "-n", str(INFRA / "scripts/backup-postgres.sh")], INFRA)

class Results(unittest.TextTestResult):
    statuses = {}

    def addSuccess(self, test):
        self.statuses[test._testMethodName] = "passed"
        super().addSuccess(test)

    def addFailure(self, test, error):
        self.statuses[test._testMethodName] = "failed"
        super().addFailure(test, error)

    def addError(self, test, error):
        self.statuses[test._testMethodName] = "failed"
        super().addError(test, error)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, help="Write a case-evidence mapping plus a sibling full report.")
    args = parser.parse_args()
    output = io.StringIO()
    runner = unittest.TextTestRunner(stream=output, verbosity=2, resultclass=Results)
    result = runner.run(unittest.defaultTestLoader.loadTestsFromTestCase(InfraConfigTests))
    print(output.getvalue(), end="")
    if args.evidence:
        evidence = args.evidence.resolve()
        evidence.parent.mkdir(parents=True, exist_ok=True)
        report = evidence.with_name("infra-config-report.json")
        report.write_text(json.dumps({"tests": result.statuses, "output": output.getvalue(), "commands": COMMANDS,
                                      "boundary": "Compose config, mocked backups and HTTPS deploy requests; no live deployment"}, indent=2))
        cases = {case: {"status": "passed" if all(result.statuses.get(test) == "passed" for test in tests) else "failed",
                        "artifact": str(report)} for case, tests in CASE_TESTS.items()}
        evidence.write_text(json.dumps(cases, indent=2))
        print(f"Case evidence: {evidence}")
    raise SystemExit(0 if result.wasSuccessful() else 1)
