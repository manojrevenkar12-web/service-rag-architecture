const BASE = import.meta.env.VITE_API_URL ?? "/api";
const KEY = import.meta.env.VITE_API_KEY ?? "demo-key";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "content-type": "application/json", "x-api-key": KEY, ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "The service is not reachable. Start it with `sra serve` and reload.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail ?? `The service answered ${res.status}.`);
  }
  return res.json() as Promise<T>;
}
