const fs = require("fs");
const path = require("path");

const WORKSPACE_ALIAS_RE = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const WORKSPACE_MAX_BYTES = 4_294_967_296;

class WorkspaceRegistryError extends Error {
  constructor(code) {
    super(code);
    this.name = "WorkspaceRegistryError";
    this.code = code;
  }
}

class WorkspaceRegistry {
  constructor({
    configPath,
    workspaceBase = "/srv/cyberboss-workspaces",
  } = {}) {
    this.configPath = requireAbsolutePath(configPath, "workspace_config_path");
    this.workspaceBase = requireAbsolutePath(workspaceBase, "workspace_base");
    this.document = readRegistryDocument(this.configPath);
    validateRegistryDocument(this.document, this.workspaceBase);
    this.defaultAlias = this.document.default_alias;
  }

  resolve(alias) {
    const normalizedAlias = normalizeAlias(alias);
    if (!WORKSPACE_ALIAS_RE.test(normalizedAlias)) {
      throw new WorkspaceRegistryError("workspace_alias_invalid");
    }
    const entry = this.document.workspaces[normalizedAlias];
    if (!entry) {
      throw new WorkspaceRegistryError("workspace_alias_unknown");
    }

    const baseStats = lstat(this.workspaceBase, "workspace_base_unavailable");
    if (baseStats.isSymbolicLink()) {
      throw new WorkspaceRegistryError("workspace_base_symlink_rejected");
    }
    const base = realDirectory(this.workspaceBase, "workspace_base_unavailable");
    const configuredRoot = path.resolve(entry.root);
    const rootStats = lstat(configuredRoot, "workspace_root_unavailable");
    if (rootStats.isSymbolicLink()) {
      throw new WorkspaceRegistryError("workspace_symlink_rejected");
    }
    if (!rootStats.isDirectory()) {
      throw new WorkspaceRegistryError("workspace_root_not_directory");
    }
    const root = realDirectory(configuredRoot, "workspace_root_unavailable");
    if (!isWithin(base, root) || root === base) {
      throw new WorkspaceRegistryError("workspace_root_escape");
    }

    return Object.freeze({
      alias: normalizedAlias,
      root,
      repo: entry.repo,
      projectSubpath: entry.project_subpath,
      maxBytes: Number(entry.max_bytes),
      sparsePaths: [...entry.sparse_paths],
      writeGlobs: [...entry.write_globs],
    });
  }

  resolveDefault() {
    return this.resolve(this.defaultAlias);
  }

  assertAllowedRoot(candidate) {
    const requested = requireAbsolutePath(candidate, "workspace_root");
    const stats = lstat(requested, "workspace_root_unavailable");
    if (stats.isSymbolicLink()) {
      throw new WorkspaceRegistryError("workspace_symlink_rejected");
    }
    if (!stats.isDirectory()) {
      throw new WorkspaceRegistryError("workspace_root_not_directory");
    }
    const realCandidate = realDirectory(requested, "workspace_root_unavailable");

    for (const alias of Object.keys(this.document.workspaces)) {
      const workspace = this.resolve(alias);
      if (workspace.root === realCandidate) {
        return workspace;
      }
    }
    throw new WorkspaceRegistryError("workspace_root_not_allowlisted");
  }

  aliasForRoot(candidate) {
    return this.assertAllowedRoot(candidate).alias;
  }
}

function readRegistryDocument(configPath) {
  const stats = lstat(configPath, "workspace_config_unavailable");
  if (stats.isSymbolicLink()) {
    throw new WorkspaceRegistryError("workspace_config_symlink_rejected");
  }
  if (!stats.isFile()) {
    throw new WorkspaceRegistryError("workspace_config_not_file");
  }
  try {
    return JSON.parse(fs.readFileSync(configPath, "utf8"));
  } catch (error) {
    if (error instanceof WorkspaceRegistryError) {
      throw error;
    }
    if (error instanceof SyntaxError) {
      throw new WorkspaceRegistryError("workspace_config_invalid_json");
    }
    throw new WorkspaceRegistryError("workspace_config_unavailable");
  }
}

function validateRegistryDocument(document, workspaceBase) {
  if (!isPlainObject(document) || document.schema_version !== 1) {
    throw new WorkspaceRegistryError("workspace_config_schema");
  }
  if (
    document.default_alias !== "cyberboss"
    || !WORKSPACE_ALIAS_RE.test(normalizeAlias(document.default_alias))
  ) {
    throw new WorkspaceRegistryError("workspace_default_alias_invalid");
  }
  if (
    document.workspace_base !== workspaceBase
    || !isPlainObject(document.workspaces)
    || JSON.stringify(Object.keys(document.workspaces)) !== JSON.stringify(["cyberboss"])
  ) {
    throw new WorkspaceRegistryError("workspace_config_empty");
  }
  if (!Object.hasOwn(document.workspaces, document.default_alias)) {
    throw new WorkspaceRegistryError("workspace_default_alias_unknown");
  }

  for (const [alias, entry] of Object.entries(document.workspaces)) {
    if (!WORKSPACE_ALIAS_RE.test(alias) || !isPlainObject(entry)) {
      throw new WorkspaceRegistryError("workspace_entry_invalid");
    }
    const root = requireAbsolutePath(entry.root, "workspace_entry_root");
    if (
      root !== path.join(workspaceBase, alias)
      || !isWithin(workspaceBase, root)
      || root === workspaceBase
    ) {
      throw new WorkspaceRegistryError("workspace_entry_outside_base");
    }
    if (entry.repo !== "LinzeColin/MetaDatabase") {
      throw new WorkspaceRegistryError("workspace_entry_repository_invalid");
    }
    if (entry.project_subpath !== "CyberBoss") {
      throw new WorkspaceRegistryError("workspace_entry_subpath_invalid");
    }
    if (
      !Number.isSafeInteger(entry.max_bytes)
      || entry.max_bytes !== WORKSPACE_MAX_BYTES
    ) {
      throw new WorkspaceRegistryError("workspace_entry_budget_invalid");
    }
    for (const key of ["sparse_paths", "write_globs"]) {
      if (!Array.isArray(entry[key]) || !entry[key].length) {
        throw new WorkspaceRegistryError(`workspace_entry_${key}_invalid`);
      }
      if (entry[key].some((value) => typeof value !== "string" || !value.trim())) {
        throw new WorkspaceRegistryError(`workspace_entry_${key}_invalid`);
      }
    }
    if (
      JSON.stringify(entry.sparse_paths) !== JSON.stringify(["CyberBoss", ".github"])
      || JSON.stringify(entry.root_integration_paths) !== JSON.stringify([".github"])
      || entry.root_integration_write !== false
      || JSON.stringify(entry.write_globs) !== JSON.stringify(["CyberBoss/**"])
    ) {
      throw new WorkspaceRegistryError("workspace_entry_scope_invalid");
    }
  }
}

function realDirectory(value, errorCode) {
  let resolved;
  try {
    resolved = fs.realpathSync.native(value);
  } catch {
    throw new WorkspaceRegistryError(errorCode);
  }
  let stats;
  try {
    stats = fs.statSync(resolved);
  } catch {
    throw new WorkspaceRegistryError(errorCode);
  }
  if (!stats.isDirectory()) {
    throw new WorkspaceRegistryError(errorCode);
  }
  return path.resolve(resolved);
}

function lstat(value, errorCode) {
  try {
    return fs.lstatSync(value);
  } catch {
    throw new WorkspaceRegistryError(errorCode);
  }
}

function requireAbsolutePath(value, label) {
  const normalized = typeof value === "string" ? value.trim() : "";
  if (!normalized || !path.isAbsolute(normalized)) {
    throw new WorkspaceRegistryError(`${label}_must_be_absolute`);
  }
  return path.resolve(normalized);
}

function isWithin(parent, candidate) {
  const relative = path.relative(path.resolve(parent), path.resolve(candidate));
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function normalizeAlias(value) {
  return typeof value === "string" ? value.trim() : "";
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

module.exports = {
  WorkspaceRegistry,
  WorkspaceRegistryError,
  WORKSPACE_ALIAS_RE,
};
