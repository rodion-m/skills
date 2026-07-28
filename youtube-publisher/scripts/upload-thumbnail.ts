import * as fs from "fs";
import * as path from "path";
import { authenticate } from "./authenticate";

interface CliOptions {
  videoId: string;
  thumbnail: string;
  attempts: number;
}

const VIDEO_ID_PATTERN = /^[A-Za-z0-9_-]{11}$/;
const SUPPORTED_EXTENSIONS = new Set([".jpg", ".jpeg", ".png"]);

function printUsage(): void {
  console.log(
    "Usage: npx ts-node upload-thumbnail.ts " +
      "--video-id VIDEO_ID --thumbnail /path/to/cover.jpg [--attempts 3]"
  );
}

function readOption(args: string[], name: string): string | undefined {
  const index = args.indexOf(name);
  if (index === -1) {
    return undefined;
  }

  const value = args[index + 1];
  if (!value || value.startsWith("--")) {
    throw new Error(`Missing value for ${name}`);
  }
  return value;
}

function parseOptions(args: string[]): CliOptions {
  if (args.includes("--help") || args.includes("-h")) {
    printUsage();
    process.exit(0);
  }

  const videoId = readOption(args, "--video-id");
  const thumbnailInput = readOption(args, "--thumbnail");
  const attemptsInput = readOption(args, "--attempts") || "3";

  if (!videoId) {
    throw new Error("--video-id is required");
  }
  if (!VIDEO_ID_PATTERN.test(videoId)) {
    throw new Error("--video-id must be an 11-character YouTube video ID");
  }
  if (!thumbnailInput) {
    throw new Error("--thumbnail is required");
  }

  const thumbnail = path.resolve(thumbnailInput);
  let thumbnailStat: fs.Stats;
  try {
    thumbnailStat = fs.statSync(thumbnail);
  } catch {
    throw new Error(`Thumbnail file does not exist: ${thumbnail}`);
  }
  if (!thumbnailStat.isFile()) {
    throw new Error(`Thumbnail path is not a file: ${thumbnail}`);
  }
  if (!SUPPORTED_EXTENSIONS.has(path.extname(thumbnail).toLowerCase())) {
    throw new Error("Thumbnail must use a .jpg, .jpeg, or .png extension");
  }
  if (thumbnailStat.size === 0) {
    throw new Error(`Thumbnail file is empty: ${thumbnail}`);
  }

  const attempts = Number(attemptsInput);
  if (!Number.isInteger(attempts) || attempts < 1 || attempts > 10) {
    throw new Error("--attempts must be an integer from 1 to 10");
  }

  return { videoId, thumbnail, attempts };
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function uploadThumbnail(options: CliOptions): Promise<void> {
  const { youtube } = await authenticate(true);
  let lastError: unknown;

  for (let attempt = 1; attempt <= options.attempts; attempt += 1) {
    try {
      console.log(`Uploading thumbnail (attempt ${attempt}/${options.attempts})...`);
      await youtube.thumbnails.set({
        videoId: options.videoId,
        media: { body: fs.createReadStream(options.thumbnail) },
      });

      const verification = await youtube.videos.list({
        part: ["snippet"],
        id: [options.videoId],
      });
      const video = verification.data.items?.[0];
      if (!video) {
        throw new Error(
          `YouTube accepted the thumbnail request, but video ${options.videoId} was not found during verification`
        );
      }

      const thumbnailKeys = Object.keys(video.snippet?.thumbnails || {});
      console.log(`VIDEO_ID: ${options.videoId}`);
      console.log(`VIDEO_URL: https://youtu.be/${options.videoId}`);
      console.log(`THUMBNAIL_FILE: ${options.thumbnail}`);
      console.log(`THUMBNAIL_VARIANTS: ${thumbnailKeys.join(",") || "unknown"}`);
      console.log("THUMBNAIL_UPLOADED: true");
      return;
    } catch (error) {
      lastError = error;
      const message = error instanceof Error ? error.message : String(error);
      console.error(`Thumbnail attempt ${attempt} failed: ${message}`);
      if (attempt < options.attempts) {
        await delay(5000);
      }
    }
  }

  console.error(`VIDEO_ID: ${options.videoId}`);
  console.error("THUMBNAIL_UPLOADED: false");
  throw lastError instanceof Error ? lastError : new Error(String(lastError));
}

async function main(): Promise<void> {
  try {
    const options = parseOptions(process.argv.slice(2));
    await uploadThumbnail(options);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`Error: ${message}`);
    printUsage();
    process.exitCode = 1;
  }
}

void main();
