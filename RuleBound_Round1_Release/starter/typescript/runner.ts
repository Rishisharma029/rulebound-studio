import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { loadAssetPack } from "./rulebound-loader.js";

const args = process.argv.slice(2);
const valueAfter = (flag: string): string => {
  const index = args.indexOf(flag);
  if (index < 0 || !args[index + 1]) throw new Error(`Missing ${flag}`);
  return args[index + 1];
};
const inputDir = valueAfter("--input");
const outputDir = valueAfter("--output");
const pack = loadAssetPack(inputDir);
const writeJson = (path: string, value: unknown) => writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");

for (const room of [...pack.rooms].sort((a, b) => String(a.room_id).localeCompare(String(b.room_id)))) {
  const roomId = String(room.room_id);
  const roomOut = join(outputDir, roomId);
  mkdirSync(roomOut, { recursive: true });
  writeJson(join(roomOut, "layout.json"), { room_id: roomId, placements: [], violations: [], status: "invalid" });
  writeJson(join(roomOut, "quote.json"), { quote_id: `QUOTE-${roomId}`, room_id: roomId, currency: "INR", lines: [], summary: { grand_total_inr: 0 }, summary_trace: [], status: "blocked", blocking_reasons: ["Starter implementation has no valid priced placements."] });
}
