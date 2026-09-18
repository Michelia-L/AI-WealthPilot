import "server-only";
import { getJson } from "./client";
import type { ProfileDetailResponse, ProfileListResponse, QuestionnaireResponse } from "./profiles";

export const getProfiles = () => getJson<ProfileListResponse>("/api/profiles");

export const getProfile = (id: number) =>
  getJson<ProfileDetailResponse>(`/api/profiles/${id}`);

export const getQuestionnaire = (locale?: string) =>
  getJson<QuestionnaireResponse>("/api/profiles/questionnaire", locale);
