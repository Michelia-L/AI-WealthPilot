import "server-only";
import { getJson } from "./client";
import type { ProfileDetailResponse, ProfileListResponse, QuestionnaireResponse } from "./profiles";
import type { ProfileGoalsResponse } from "./goals";

export const getProfiles = () => getJson<ProfileListResponse>("/api/profiles");

export const getProfile = (id: number) =>
  getJson<ProfileDetailResponse>(`/api/profiles/${id}`);

export const getQuestionnaire = (locale?: string) =>
  getJson<QuestionnaireResponse>("/api/profiles/questionnaire", locale);

export const getProfileGoals = (id: number, locale: string) =>
  getJson<ProfileGoalsResponse>(`/api/profiles/${id}/goals`, locale);
