import { fal } from "@fal-ai/client";

export async function POST(req: Request) {
  const falKey = process.env.FAL_KEY;
  if (!falKey) {
    return Response.json({ error: "FAL_KEY not configured" }, { status: 503 });
  }

  const { address, lat, lng, municipality } = await req.json();

  if (!address || !municipality) {
    return Response.json({ error: "address and municipality are required" }, { status: 400 });
  }

  fal.config({ credentials: falKey });

  try {
    const coordinates =
      typeof lat === "number" && typeof lng === "number" ? ` near (${lat}, ${lng})` : "";
    const result = await fal.subscribe("fal-ai/veo3", {
      input: {
        prompt: `Aerial drone flyover of ${address}${coordinates} in ${municipality}, Florida. Real estate development context, cinematic quality, golden hour lighting with warm amber sky, smooth cinematic camera arc slowly revealing the property and surrounding neighborhood, 8K resolution, professional real estate videography.`,
        duration: "8s",
        aspect_ratio: "16:9",
        generate_audio: false,
        resolution: "1080p",
      },
    });

    const videoUrl = (result.data as { video?: { url?: string } }).video?.url;
    if (!videoUrl) {
      return Response.json({ error: "No video URL in response" }, { status: 502 });
    }

    return Response.json({ videoUrl });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Video generation failed";
    return Response.json({ error: message }, { status: 502 });
  }
}
