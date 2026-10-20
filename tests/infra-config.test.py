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

INFRA = Path(__file__).resolve().parents[1]
API = Path(os.environ.get("API_REPO", INFRA.parent / "boero-api")).resolve()
UI = Path(os.environ.get("UI_REPO", INFRA.parent / "boero-ui")).resolve()
COMMANDS = []
OLD_SHA = "a" * 40
NEW_SHA = "b" * 40
OTHER_SHA = "c" * 40
CASE_TESTS = {
    "Q01.isolated-compose": ["test_compose_isolation", "test_dokploy_staging_compose", "test_local_acceptance_compose"],
    "Q02.persistent-readiness": ["test_persistent_profile", "test_postgres_final_readiness"],
    "Q03.legacy-operations": ["test_legacy_operations", "test_bootstrap_order"],
    "Q04.invalid-input": ["test_invalid_inputs", "test_preflight_preservation"],
    "Q04.failed-deploy-rollback": ["test_unhealthy_rollback", "test_api_initialization_failure"],
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
        self.temporary = tempfile.TemporaryDirectory(prefix="boero-infra-config-")
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)

    def render(self, environment, values):
        env_file = self.work / f"synthetic-{environment}.env"
        write_env(env_file, values)
        result = command(["docker", "compose", "--profile", "maintenance", "--env-file", str(env_file),
                          "-f", str(INFRA / "compose.yaml"), "-f", str(INFRA / f"compose.{environment}.yaml"),
                          "config", "--format", "json"], INFRA, cli_environment())
        return json.loads(result.stdout)

    def mocked_workspace(self):
        for name in ("Makefile", "compose.yaml", "compose.staging.yaml", "compose.production.yaml"):
            shutil.copy2(INFRA / name, self.work / name)
        shutil.copytree(INFRA / "scripts", self.work / "scripts")
        for environment in ("staging", "production"):
            values = synthetic_env()
            values["BACKUP_DIR"] = str(self.work / "backups")
            values["BACKUP_RETENTION_DAYS"] = "7"
            write_env(self.work / f".env.{environment}", values)
        bindir = self.work / "bin"
        bindir.mkdir()
        docker = bindir / "docker"
        docker.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
args=sys.argv[1:]
with open(os.environ['DOCKER_TRACE'], 'a') as stream:
    stream.write(json.dumps(args)+'\\n')
if args[:2] == ['volume', 'create']:
    print(args[2]); sys.exit(0)
if args[0] != 'compose': sys.exit(9)
if os.environ.get('FAIL_PREFLIGHT') == 'true' and args[-2:] == ['config','--quiet']:
    sys.exit(2)
envfile=pathlib.Path(args[args.index('--env-file')+1])
values=dict(line.split('=',1) for line in envfile.read_text().splitlines() if '=' in line)
if 'up' in args and os.environ.get('FAIL_NEW_VERSION') == 'true':
    key='API_VERSION' if args[-1] == 'api' else 'UI_VERSION'
    if values[key] == 'sha-'+('b'*40): sys.exit(3)
if 'api-storage-init' in args and os.environ.get('FAIL_STORAGE_INIT') == 'true':
    if values['API_VERSION'] == 'sha-'+('b'*40): sys.exit(4)
if 'exec' in args and 'postgres' in args:
    if any('pg_dump' in arg for arg in args): print('synthetic-custom-dump')
    if 'pg_restore' in args:
        if not sys.stdin.read().startswith('synthetic-custom-dump'): sys.exit(5)
''')
        docker.chmod(0o755)
        self.trace = self.work / "docker.jsonl"
        self.env = cli_environment() | {"PATH": str(bindir) + ":" + os.environ["PATH"], "DOCKER_TRACE": str(self.trace)}

    def trace_commands(self):
        return [json.loads(line) for line in self.trace.read_text().splitlines()] if self.trace.exists() else []

    def make(self, target, extra=(), env=None, check=True):
        return command(["make", target, "ENV=production", *extra], self.work, self.env | (env or {}), check)

    def preserved(self):
        return {name: (self.work / name).read_bytes() for name in (".env.staging",)}

    def assert_preserved(self, baseline):
        for name, value in baseline.items():
            self.assertEqual((self.work / name).read_bytes(), value)
        self.assertFalse((self.work / ".deploy/staging").exists())

    def test_compose_isolation(self):
        configs = {environment: self.render(environment, synthetic_env()) for environment in ("staging", "production")}
        staging, production = configs["staging"], configs["production"]
        self.assertTrue({v["name"] for v in staging["volumes"].values()}.isdisjoint(
            v["name"] for v in production["volumes"].values()))
        self.assertNotEqual(staging["networks"]["default"]["name"], production["networks"]["default"]["name"])
        for configured in configs.values():
            services = configured["services"]
            for service in ("postgres", "redis"):
                self.assertNotIn("ports", services[service])
            self.assertEqual(services["ui"]["environment"]["FRONTEND_PUBLIC_URL"], "")
            self.assertEqual(services["postgres"]["image"], "postgres:18-alpine")
            self.assertIn("readiness", " ".join(services["api"]["healthcheck"]["test"]))
            self.assertIn("pg_isready", " ".join(services["postgres"]["healthcheck"]["test"]))
            helper = services["api-storage-init"]
            self.assertEqual(helper["image"], services["api"]["image"])
            self.assertEqual(helper["network_mode"], "none")
            self.assertEqual([v["source"] for v in helper["volumes"]], ["api-storage"])

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
            "ui-next-cache": "boero-ui-next-cache-staging",
            "postgres-data": "boero-api-postgres-data-staging",
            "redis-data": "boero-api-redis-data-staging",
            "api-logs": "boero-api-logs-staging",
            "api-storage": "boero-api-enrollment-storage-staging",
        }
        self.assertEqual(configured["volumes"], {key: {"external": True, "name": name}
                                                 for key, name in expected_volumes.items()})
        services = configured["services"]
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
        self.assertEqual(configured["networks"]["default"]["name"], "boero-network-staging")
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
        state = {"namespace": "boero-acceptance-synthetic", "owner": "synthetic-owner", "tlsPort": 8443,
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
        guard = API / "src/main/java/ar/edu/utn/frvm/typeit/boero_api/auth/config/WebAuthnDeploymentGuard.java"
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

    def test_legacy_operations(self):
        self.mocked_workspace()
        baseline = self.preserved()
        for target in ("prepare", "preflight", "status", "logs", "logs-api", "logs-api-file", "down"):
            self.make(target)
        self.make("logs-api-request", ["REQUEST_ID=synthetic-id"])
        self.make("deploy-ui", ["VERSION=sha-" + NEW_SHA])
        self.assertIn("UI_VERSION=sha-" + NEW_SHA, (self.work / ".env.production").read_text())
        self.make("rollback-ui")
        self.assertIn("UI_VERSION=sha-" + OLD_SHA, (self.work / ".env.production").read_text())
        self.make("deploy-api", ["VERSION=sha-" + NEW_SHA])
        self.make("rollback-api")
        self.assertIn("API_VERSION=sha-" + OTHER_SHA, (self.work / ".env.production").read_text())
        self.make("backup-db")
        archives = list((self.work / "backups/production").glob("*.dump"))
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0].stat().st_mode & 0o777, 0o600)
        self.assertFalse(list((self.work / "backups/production").glob("*.tmp")))
        commands = self.trace_commands()
        volumes = {cmd[2] for cmd in commands if cmd[:2] == ["volume", "create"]}
        self.assertEqual(volumes, {f"boero-{name}-prod" for name in
                                  ("ui-next-cache", "api-postgres-data", "api-redis-data", "api-logs", "api-enrollment-storage")})
        for args in commands:
            if args[0] == "compose":
                self.assertIn("compose.production.yaml", args)
                self.assertNotIn("compose.staging.yaml", args)
        self.assertTrue(any("--remove-orphans" in args for args in commands))
        self.assertFalse(any("--volumes" in args for args in commands))
        self.assert_preserved(baseline)

    def test_bootstrap_order(self):
        self.mocked_workspace()
        self.make("bootstrap")
        commands = self.trace_commands()
        self.assertEqual(commands[0][-2:], ["config", "--quiet"])
        self.assertEqual(commands[1][:2], ["volume", "create"])
        pull = next(i for i, cmd in enumerate(commands) if cmd[-1:] == ["pull"])
        initialize = next(i for i, cmd in enumerate(commands) if "api-storage-init" in cmd)
        up = next(i for i, cmd in enumerate(commands) if "up" in cmd)
        self.assertLess(pull, initialize)
        self.assertLess(initialize, up)
        self.assertIn("--wait", commands[up])

    def test_invalid_inputs(self):
        self.mocked_workspace()
        baseline = self.preserved() | {".env.production": (self.work / ".env.production").read_bytes()}
        targets = ("prepare", "preflight", "bootstrap", "deploy-api", "deploy-ui", "rollback-api", "rollback-ui", "backup-db", "status", "logs", "down")
        for environment in ("bad", "../staging", "%", "staging production", "qa"):
            for target in targets:
                result = command(["make", target, "ENV=" + environment, "VERSION=sha-" + NEW_SHA], self.work, self.env, False)
                self.assertNotEqual(result.returncode, 0)
        for script in ("prepare-volumes.sh", "bootstrap.sh", "deploy-service.sh", "rollback-service.sh", "backup-postgres.sh"):
            self.assertNotEqual(command(["./scripts/" + script, "unknown", "api", "sha-" + NEW_SHA], self.work, self.env, False).returncode, 0)
        for version in ("", "develop", "sha-" + "B" * 40, "sha-" + "z" * 40,
                        "sha-abcd;touch injected", "sha-$$(touch injected)"):
            self.assertNotEqual(self.make("deploy-api", ["VERSION=" + version], check=False).returncode, 0)
        self.assertEqual(self.trace_commands(), [])
        self.assertFalse((self.work / "injected").exists())
        self.assertFalse((self.work / ".deploy").exists())
        self.assert_preserved(baseline)

    def test_preflight_preservation(self):
        self.mocked_workspace()
        baseline = self.preserved() | {".env.production": (self.work / ".env.production").read_bytes()}
        for target in ("bootstrap", "deploy-api", "deploy-ui"):
            self.assertNotEqual(self.make(target, ["VERSION=sha-" + NEW_SHA], {"FAIL_PREFLIGHT": "true"}, False).returncode, 0)
        self.assertTrue(all(args[-2:] == ["config", "--quiet"] for args in self.trace_commands()))
        self.assertFalse((self.work / ".deploy").exists())
        self.assert_preserved(baseline)

    def test_unhealthy_rollback(self):
        self.mocked_workspace()
        baseline = self.preserved()
        for service, previous in (("ui", OLD_SHA), ("api", OTHER_SHA)):
            with self.subTest(service=service):
                before = (self.work / ".env.production").read_bytes()
                start = len(self.trace_commands())
                self.assertNotEqual(self.make("deploy-" + service, ["VERSION=sha-" + NEW_SHA],
                                              {"FAIL_NEW_VERSION": "true"}, False).returncode, 0)
                self.assertEqual((self.work / ".env.production").read_bytes(), before)
                up_commands = [args for args in self.trace_commands()[start:] if "up" in args]
                self.assertEqual(len(up_commands), 2)
                self.assertIn("--wait", up_commands[0])
                self.assertEqual((self.work / f".deploy/production/{service}.previous").read_text().strip(), "sha-" + previous)
                self.assert_preserved(baseline)

    def test_api_initialization_failure(self):
        self.mocked_workspace()
        before = (self.work / ".env.production").read_bytes()
        self.assertNotEqual(self.make("deploy-api", ["VERSION=sha-" + NEW_SHA], {"FAIL_STORAGE_INIT": "true"}, False).returncode, 0)
        self.assertEqual((self.work / ".env.production").read_bytes(), before)
        commands = self.trace_commands()
        # Failed candidate initializer never reaches startup; only restored image is started.
        self.assertEqual(sum("api-storage-init" in args for args in commands), 2)
        self.assertEqual(sum("up" in args for args in commands), 1)

    def test_publication_gates(self):
        for repo, expected in ((API, "[static-analysis, test]"), (UI, "verify")):
            workflow = (repo / ".github/workflows/ci.yaml").read_text()
            publish = job(workflow, "publish-image")
            self.assertEqual(scalar(publish, 4, "needs"), expected)
            for event in ("push", "pull_request", "workflow_dispatch"):
                for ref in ("develop", "staging", "main", "feature/example"):
                    self.assertEqual(condition(publish, event, ref), event == "push" and ref in ("develop", "staging", "main"))
            self.assertIn("sha-${{ github.sha }}", publish)
            self.assertIn("push: true", publish)
            if repo == API:
                self.assertIn("staticAnalysis", job(workflow, "static-analysis"))
                self.assertIn("spotlessCheck fastTest", job(workflow, "test"))
                self.assertIn("integrationTest", job(workflow, "test"))
                self.assertIn("spotlessCheck test", job(workflow, "test"))
            else:
                for gate in ("format:check", "lint", "typecheck", "test --runInBand", "build"):
                    self.assertIn("run: pnpm " + gate, job(workflow, "verify"))

    def test_existing_flows(self):
        for repo in (API, UI):
            workflow_path = ".github/workflows/ci.yaml"
            before = command(["git", "show", "HEAD:" + workflow_path], repo).stdout
            after = (repo / workflow_path).read_text()
            self.assertEqual(before.replace(job(before, "deploy-staging"), ""),
                             after.replace(job(after, "deploy-staging"), ""))
            production_path = ".github/workflows/deploy-production.yaml"
            self.assertEqual(command(["git", "show", "HEAD:" + production_path], repo).stdout, (repo / production_path).read_text())
        values = synthetic_env() | {
            "AUTO_LOGIN_ENABLED": "true",
            "AUTO_LOGIN_USER_ID": "00000000-0000-0000-0000-000000000001",
            "AUTO_LOGIN_INSTITUTION_ID": "00000000-0000-0000-0000-000000000002",
        }
        for environment, profile in (("staging", "staging"), ("production", "prod")):
            rendered = self.render(environment, values)
            self.assertEqual(rendered["name"], f"boero-{environment}")
            self.assertEqual(rendered["networks"]["default"]["name"], f"boero-network-{environment}")
            self.assertEqual(rendered["services"]["api"]["environment"]["SPRING_PROFILES_ACTIVE"], profile)
            for service in ("ui", "api", "postgres", "redis"):
                configured = rendered["services"][service]
                self.assertEqual(configured["container_name"], f"boero-{service}-{environment}")
                for port in configured.get("ports", []):
                    self.assertEqual(port["host_ip"], "127.0.0.1")
                for key in ("AUTO_LOGIN_ENABLED", "AUTO_LOGIN_USER_ID", "AUTO_LOGIN_INSTITUTION_ID"):
                    if environment == "staging" and (service == "api" or service == "ui" and key == "AUTO_LOGIN_ENABLED"):
                        self.assertEqual(configured["environment"][key], values[key])
                    else:
                        self.assertNotIn(key, configured.get("environment", {}))

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
                                                    "GITHUB_REPOSITORY": "typeitorg/boero-synthetic"}
        for repo in (API, UI):
            workflow = (repo / ".github/workflows/ci.yaml").read_text()
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
                              "title": "typeitorg/boero-synthetic@" + NEW_SHA})
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
        self.assertIn("ya no describe estos archivos", (INFRA / "docs/STAGING.md").read_text())
        for script in ("prepare-volumes.sh", "bootstrap.sh", "deploy-service.sh", "rollback-service.sh", "backup-postgres.sh"):
            command(["sh", "-n", str(INFRA / "scripts" / script)], INFRA)

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
                                      "boundary": "config, mocked Docker orchestration, local Git workflow validation; no live deployment"}, indent=2))
        cases = {case: {"status": "passed" if all(result.statuses.get(test) == "passed" for test in tests) else "failed",
                        "artifact": str(report)} for case, tests in CASE_TESTS.items()}
        evidence.write_text(json.dumps(cases, indent=2))
        print(f"Case evidence: {evidence}")
    raise SystemExit(0 if result.wasSuccessful() else 1)
