import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

export type JsonObject = Record<string, unknown>;
export interface AssetPack {
  catalog: JsonObject[];
  finishes: JsonObject[];
  rules: JsonObject;
  rooms: JsonObject[];
  briefs: Record<string, string>;
  historicalJobs: JsonObject[];
}

const readJson = <T>(path: string): T => JSON.parse(readFileSync(path, "utf8")) as T;

export function loadAssetPack(inputDir: string): AssetPack {
  const roomDir = join(inputDir, "rooms");
  const briefDir = join(inputDir, "briefs");
  const roomFiles = readdirSync(roomDir).filter((name) => name.endsWith(".json")).sort();
  const briefFiles = readdirSync(briefDir).filter((name) => name.endsWith(".txt")).sort();
  return {
    catalog: readJson<JsonObject[]>(join(inputDir, "catalog.json")),
    finishes: readJson<JsonObject[]>(join(inputDir, "finishes.json")),
    rules: readJson<JsonObject>(join(inputDir, "rules.json")),
    rooms: roomFiles.map((name) => readJson<JsonObject>(join(roomDir, name))),
    briefs: Object.fromEntries(briefFiles.map((name) => [name.replace(/\.txt$/, ""), readFileSync(join(briefDir, name), "utf8").trim()])),
    historicalJobs: readJson<JsonObject[]>(join(inputDir, "historical_jobs.json")),
  };
}
