import { advisor } from "./advisor";
import { clientSelector } from "./clientSelector";
import { common } from "./common";
import { deliverableDetail } from "./deliverableDetail";
import { deliverables } from "./deliverables";
import { errors } from "./errors";
import { health } from "./health";
import { ips } from "./ips";
import { market } from "./market";
import { meta } from "./meta";
import { monitoring } from "./monitoring";
import { nav } from "./nav";
import { optimizer } from "./optimizer";
import { overview } from "./overview";
import { profileDetail } from "./profileDetail";
import { profiles } from "./profiles";
import { retirement } from "./retirement";
import { settings } from "./settings";

export const en = {
  advisor,
  clientSelector,
  common,
  deliverableDetail,
  deliverables,
  errors,
  health,
  ips,
  market,
  meta,
  monitoring,
  nav,
  optimizer,
  overview,
  profileDetail,
  profiles,
  retirement,
  settings,
};

/** Type source of truth — zh must satisfy this shape (compile-time checked). */
export type Dictionary = typeof en;
