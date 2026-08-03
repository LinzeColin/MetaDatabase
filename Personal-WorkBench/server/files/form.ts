import { rejectClientTenantFields } from "@/server/security/tenant";
import {
  isPrivateFileModule,
  PrivateFileInputError,
  validatePrivateImageUpload,
  type PrivateFileModule,
} from "./private-files";

export async function readPrivateFileForm(request: Request): Promise<{
  module: PrivateFileModule;
  buffer: ArrayBuffer;
  validated: { contentType: string; byteSize: number; sha256: string; width: number; height: number };
}> {
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    throw new PrivateFileInputError();
  }

  const keys = Array.from(form.keys());
  if (keys.some((key) => key !== "module" && key !== "file")) throw new PrivateFileInputError();
  rejectClientTenantFields(
    Object.fromEntries(Array.from(form.entries()).filter(([, value]) => typeof value === "string")),
  );

  const moduleName = form.get("module");
  const file = form.get("file");
  if (typeof moduleName !== "string" || !isPrivateFileModule(moduleName)) throw new PrivateFileInputError();
  if (!file || typeof file === "string" || typeof file.arrayBuffer !== "function" || typeof file.type !== "string") {
    throw new PrivateFileInputError();
  }

  const buffer = await file.arrayBuffer();
  return {
    module: moduleName,
    buffer,
    validated: await validatePrivateImageUpload(file.type, buffer),
  };
}
