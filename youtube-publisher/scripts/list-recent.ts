import { authenticate } from "./authenticate";
import { google } from "googleapis";

async function main() {
  const { oauth2Client: auth } = await authenticate(false);
  const youtube = google.youtube({ version: "v3", auth });

  const channels = await youtube.channels.list({ part: ["contentDetails", "snippet"], mine: true });
  const ch: any = (channels.data as any).items[0];
  const uploadsPlaylist = ch.contentDetails.relatedPlaylists.uploads;
  console.log("Channel:", ch.snippet.title);

  const pl = await youtube.playlistItems.list({ part: ["snippet"], playlistId: uploadsPlaylist, maxResults: 15 });
  const ids: string[] = pl.data.items!.map((i: any) => i.snippet.resourceId.videoId);
  const vids = await youtube.videos.list({ part: ["snippet", "status"], id: ids });

  for (const v of vids.data.items!) {
    const thumbs: any = (v as any).snippet.thumbnails;
    console.log("---");
    console.log("ID:", v.id);
    console.log("Title:", (v as any).snippet.title);
    console.log("Privacy:", (v as any).status.privacyStatus);
    console.log("Published:", (v as any).snippet.publishedAt);
    console.log("Thumb keys:", Object.keys(thumbs).join(","));
  }

  // 字幕检查：对最近 3 个视频
  for (const id of ids.slice(0, 4)) {
    try {
      const caps = await youtube.captions.list({ part: ["snippet"], videoId: id });
      const n = caps.data.items?.length || 0;
      console.log(`\nCaptions ${id}: ${n}`);
      for (const c of caps.data.items || []) console.log("  -", (c as any).snippet.language, (c as any).snippet.name);
    } catch (e: any) { console.log(`captions err ${id}:`, e.message); }
  }
}
main().catch(e => { console.error(e); process.exit(1); });
