import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const REPOSITORY_ROOT = resolve(ROOT, "..");
const CONTRACT_PATH = join(ROOT, "SOURCE_PROJECTION_CONTRACT.json");

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd,
    encoding: options.encoding ?? "utf8",
    env: options.env ?? process.env,
    input: options.input,
    maxBuffer: options.maxBuffer ?? 64 * 1024 * 1024,
  });
  if (result.error) throw result.error;
  assert.equal(result.status, 0, command + " " + args.join(" ") + " failed: " + String(result.stderr).trim());
  return result.stdout;
}

function runBinary(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd,
    encoding: "buffer",
    env: options.env ?? process.env,
    maxBuffer: options.maxBuffer ?? 64 * 1024 * 1024,
  });
  if (result.error) throw result.error;
  assert.equal(result.status, 0, command + " " + args.join(" ") + " failed: " + String(result.stderr).trim());
  return result.stdout;
}

function trim(value) {
  return String(value).trim();
}

async function main() {
  const contract = JSON.parse(await readFile(CONTRACT_PATH, "utf8"));
  const { source, projection } = contract;
  assert.equal(contract.contract_id, "PWB-S5-SOURCE-PROJECTION-001");
  assert.equal(source.repository, "MetaDatabase");
  assert.equal(source.project_path, "Personal-WorkBench");
  assert.match(source.commit, /^[0-9a-f]{40}$/);
  assert.match(source.root_tree, /^[0-9a-f]{40}$/);
  assert.match(source.project_tree, /^[0-9a-f]{40}$/);
  assert.match(projection.commit, /^[0-9a-f]{40}$/);
  assert.equal(projection.parent, null);

  const sourceCommit = trim(run("git", ["-C", REPOSITORY_ROOT, "rev-parse", source.commit + "^{commit}"]));
  const sourceRootTree = trim(run("git", ["-C", REPOSITORY_ROOT, "rev-parse", source.commit + "^{tree}"]));
  const sourceProjectTree = trim(run("git", ["-C", REPOSITORY_ROOT, "rev-parse", source.commit + ":" + source.project_path]));
  const sourceFileCount = Number(
    trim(run("git", ["-C", REPOSITORY_ROOT, "ls-tree", "-r", "--name-only", source.commit, "--", source.project_path]))
      .split("\n")
      .filter(Boolean).length,
  );

  assert.equal(sourceCommit, source.commit);
  assert.equal(sourceRootTree, source.root_tree);
  assert.equal(sourceProjectTree, source.project_tree);
  assert.equal(sourceFileCount, source.tracked_file_count);

  const temporaryRoot = await mkdtemp(join(tmpdir(), "pwb-source-projection-"));
  const projectRoot = join(temporaryRoot, source.project_path);
  try {
    await mkdir(projectRoot, { recursive: true });
    const archive = runBinary("git", ["-C", REPOSITORY_ROOT, "archive", source.commit + ":" + source.project_path]);
    run("tar", ["-x", "-C", projectRoot], { input: archive, encoding: "buffer" });

    run("git", ["-C", projectRoot, "init", "-q", "-b", projection.branch]);
    run("git", ["-C", projectRoot, "add", "-A"]);
    const projectionTree = trim(run("git", ["-C", projectRoot, "write-tree"]));
    assert.equal(projectionTree, source.project_tree);
    assert.equal(projectionTree, projection.tree);

    const identityEnv = {
      ...process.env,
      GIT_AUTHOR_NAME: projection.author_name,
      GIT_AUTHOR_EMAIL: projection.author_email,
      GIT_AUTHOR_DATE: projection.timestamp_utc,
      GIT_COMMITTER_NAME: projection.author_name,
      GIT_COMMITTER_EMAIL: projection.author_email,
      GIT_COMMITTER_DATE: projection.timestamp_utc,
    };
    const message = projection.commit_message_lines.join("\n") + "\n";
    const projectionCommit = trim(
      run("git", ["-C", projectRoot, "commit-tree", projectionTree], { env: identityEnv, input: message }),
    );
    const projectionTreeReadback = trim(run("git", ["-C", projectRoot, "rev-parse", projectionCommit + "^{tree}"]));
    const projectionFileCount = Number(trim(run("git", ["-C", projectRoot, "ls-files"])).split("\n").filter(Boolean).length);
    const parentProbe = spawnSync("git", ["-C", projectRoot, "rev-parse", projectionCommit + "^"], { encoding: "utf8" });

    assert.equal(projectionCommit, projection.commit);
    assert.equal(projectionTreeReadback, source.project_tree);
    assert.equal(projectionFileCount, source.tracked_file_count);
    assert.notEqual(parentProbe.status, 0, "projection commit must have no parent");

    console.log(
      JSON.stringify({
        status: "PASS_SOURCE_PROJECTION_CONTRACT",
        product_pass_claimed: false,
        remote_action_taken: false,
        source: {
          commit: sourceCommit,
          root_tree: sourceRootTree,
          project_tree: sourceProjectTree,
          tracked_file_count: sourceFileCount,
        },
        projection: {
          commit: projectionCommit,
          tree: projectionTreeReadback,
          tracked_file_count: projectionFileCount,
          parent: null,
        },
      }),
    );
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 1;
});
