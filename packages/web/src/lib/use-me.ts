"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { ApiError, api, type MeDTO } from "./api";

/**
 * Pulls the current user from `/auth/me`.
 *
 * A 401 is *not* an error from the caller's POV — it just means "no one is
 * signed in." `data: null` is the sentinel; consumers can branch on that.
 */
export function useMe(): UseQueryResult<MeDTO | null> {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await api.me();
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          return null as unknown as MeDTO;
        }
        throw err;
      }
    },
    staleTime: 5 * 60_000,
    refetchInterval: false,
    retry: (failureCount, err) =>
      err instanceof ApiError && err.status === 401 ? false : failureCount < 1,
  });
}
