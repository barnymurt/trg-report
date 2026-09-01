import { headers } from "next/headers";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export async function api<T>(
  path: string,
  init: RequestInit = {},
  token?: string,
): Promise<T> {
  const headersList = new Headers(init.headers);
  headersList.set("Content-Type", "application/json");
  if (token) headersList.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${API_URL}${path}`, { ...init, headers: headersList });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export async function apiForm<T>(
  path: string,
  form: FormData,
  token?: string,
): Promise<T> {
  const headersList = new Headers();
  if (token) headersList.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    body: form,
    headers: headersList,
  });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export async function apiBinary(
  path: string,
  init: RequestInit = {},
): Promise<ArrayBuffer> {
  const res = await fetch(`${API_URL}${path}`, init);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.arrayBuffer();
}
