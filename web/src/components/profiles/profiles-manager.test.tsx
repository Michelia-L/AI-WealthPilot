import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  ProfileCompareResponse,
  ProfilePayload,
  ProfileSummary,
  QuestionnaireResponse,
} from "@/lib/api";
import { common } from "@/lib/i18n/dictionaries/en/common";
import { profiles as profilesDict } from "@/lib/i18n/dictionaries/en/profiles";
import ProfilesManager from "./profiles-manager";
import { MAX_COMPARE } from "./shared";

// Real English dictionary; children are stubbed so the manager's
// orchestration (modes, payloads, dialogs) is what gets tested.
vi.mock("@/components/locale-context", () => ({
  useT: () => ({ profiles: profilesDict, common }),
  useLocale: () => ({ locale: "en" }),
}));
const refreshMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: refreshMock }),
}));

interface ListMockProps {
  profiles: ProfileSummary[] | null;
  selected: number[];
  onToggleSelect: (id: number) => void;
  onCompare: () => void;
  notice: string | null;
  error: string | null;
  onImport: () => void;
  onEdit: (id: number) => void;
  onDelete: (p: ProfileSummary) => void;
  onCreate: () => void;
}
vi.mock("./profile-list", () => ({
  default: (p: ListMockProps) => (
    <div data-testid="profile-list">
      {p.profiles?.map((pr) => (
        <span key={pr.id}>
          <button onClick={() => p.onToggleSelect(pr.id)}>sel-{pr.id}</button>
          <button onClick={() => p.onEdit(pr.id)}>edit-{pr.id}</button>
          <button onClick={() => p.onDelete(pr)}>del-{pr.id}</button>
        </span>
      ))}
      <button onClick={p.onCompare}>compare</button>
      <button onClick={p.onImport}>import</button>
      <span data-testid="selected-count">{p.selected.length}</span>
      {p.notice && <span data-testid="notice">{p.notice}</span>}
      {p.error && <span data-testid="list-error">{p.error}</span>}
    </div>
  ),
}));

interface FormMockProps {
  mode: string;
  form: ProfilePayload;
  error: string | null;
  setAnswer: (track: "ability_answers", q: string, o: string) => void;
  onSave: () => void;
  onCancel: () => void;
}
vi.mock("./profile-form", () => ({
  default: (p: FormMockProps) => (
    <div data-testid="profile-form">
      <span data-testid="form-mode">{p.mode}</span>
      <span data-testid="form-name">{p.form.name}</span>
      <span data-testid="form-answers">
        {JSON.stringify(p.form.ability_answers)}
      </span>
      {p.error && <span data-testid="form-error">{p.error}</span>}
      {/* exercises the manager's real setAnswer toggle logic */}
      <button onClick={() => p.setAnswer("ability_answers", "q1", "a")}>
        answer-a
      </button>
      <button onClick={p.onSave}>save</button>
      <button onClick={p.onCancel}>cancel</button>
    </div>
  ),
}));

vi.mock("./profile-compare", () => ({
  default: ({ result }: { result: ProfileCompareResponse }) => (
    <div data-testid="compare-panel">{result.profiles.length} compared</div>
  ),
}));

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status });
}

const SUMMARIES = [1, 2, 3].map(
  (id) =>
    ({
      id,
      name: `Client ${id}`,
      age: 30 + id,
      risk_level: "Balanced / 平衡型",
    }) as ProfileSummary
);

const EDIT_PAYLOAD = {
  name: "  Jane  ",
  age: 45,
  marital_status: "married",
  dependents: 2,
  financial: {
    annual_income: 100000,
    annual_expenses: 60000,
    investable_assets: 500000,
    total_liabilities: 100000,
    emergency_fund_months: 6,
  },
  goals: [],
  time_horizon_years: 20,
  is_multi_stage: false,
  liquidity_needs: 0.1,
  tax_status: "taxable",
  esg_preference: false,
  sector_restrictions: [" Tobacco ", "Weapons"],
  notes: "",
  risk_scores: { ability_score: 3, willingness_score: 3.5 },
  ability_answers: {},
  willingness_answers: {},
} as ProfilePayload;

function renderManager(overrides: {
  initialProfiles?: ProfileSummary[] | null;
  questionnaire?: QuestionnaireResponse | null;
  initialEdit?: { id: number; payload: ProfilePayload } | null;
} = {}) {
  return render(
    <ProfilesManager
      initialProfiles={overrides.initialProfiles ?? SUMMARIES}
      questionnaire={overrides.questionnaire ?? null}
      initialEdit={overrides.initialEdit}
    />
  );
}

beforeEach(() => {
  fetchMock.mockReset();
  refreshMock.mockClear();
});

describe("ProfilesManager modes", () => {
  it("switches list → create → save (POST) → back to list", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse({ id: 9 }, 201))
    );
    renderManager();

    fireEvent.click(screen.getByRole("button", { name: "New Profile" }));
    expect(screen.getByTestId("form-mode")).toHaveTextContent("create");

    fireEvent.click(screen.getByRole("button", { name: "save" }));
    await waitFor(() =>
      expect(screen.getByTestId("profile-list")).toBeInTheDocument()
    );

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/profiles");
    expect((init as RequestInit).method).toBe("POST");
    expect(refreshMock).toHaveBeenCalled();
  });

  it("deep-link edit: PUTs the trimmed name and parsed restrictions", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ id: 7 })));
    renderManager({ initialEdit: { id: 7, payload: EDIT_PAYLOAD } });

    expect(screen.getByTestId("form-mode")).toHaveTextContent("edit");
    expect(screen.getByTestId("form-name")).toHaveTextContent("Jane");

    fireEvent.click(screen.getByRole("button", { name: "save" }));
    await waitFor(() => expect(refreshMock).toHaveBeenCalled());

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/profiles/7");
    expect((init as RequestInit).method).toBe("PUT");
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.name).toBe("Jane");
    expect(body.sector_restrictions).toEqual(["Tobacco", "Weapons"]);
  });

  it("cancel returns to the list without saving", () => {
    renderManager();
    fireEvent.click(screen.getByRole("button", { name: "New Profile" }));
    fireEvent.click(screen.getByRole("button", { name: "cancel" }));
    expect(screen.getByTestId("profile-list")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("toggles questionnaire answers off on a repeated click", () => {
    renderManager();
    fireEvent.click(screen.getByRole("button", { name: "New Profile" }));

    fireEvent.click(screen.getByRole("button", { name: "answer-a" }));
    expect(screen.getByTestId("form-answers")).toHaveTextContent('{"q1":"a"}');
    // clicking the same option again clears it
    fireEvent.click(screen.getByRole("button", { name: "answer-a" }));
    expect(screen.getByTestId("form-answers")).toHaveTextContent("{}");
  });
});

describe("ProfilesManager list actions", () => {
  it("deletes through the confirm dialog", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(new Response(null, { status: 204 }))
    );
    renderManager();

    fireEvent.click(screen.getByRole("button", { name: "del-2" }));
    expect(screen.getByText("Delete Client Profile")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(refreshMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/profiles/2");
    expect((init as RequestInit).method).toBe("DELETE");
  });

  it("compares selected profiles", async () => {
    const compare: ProfileCompareResponse = {
      comparison_date: "2026-08-15",
      insights: [],
      profiles: [{}, {}] as ProfileCompareResponse["profiles"],
    };
    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse(compare))
    );
    renderManager();

    fireEvent.click(screen.getByRole("button", { name: "sel-1" }));
    fireEvent.click(screen.getByRole("button", { name: "sel-3" }));
    fireEvent.click(screen.getByRole("button", { name: "compare" }));

    expect(await screen.findByTestId("compare-panel")).toHaveTextContent(
      "2 compared"
    );
    expect(fetchMock.mock.calls[0][0]).toBe("/api/profiles/compare?ids=1,3");
  });

  it("caps the compare selection at MAX_COMPARE", () => {
    const many = Array.from({ length: MAX_COMPARE + 2 }, (_, i) => ({
      id: i + 1,
      name: `C${i + 1}`,
      age: 30,
      risk_level: "",
    })) as ProfileSummary[];
    renderManager({ initialProfiles: many });

    for (const p of many) {
      fireEvent.click(screen.getByRole("button", { name: `sel-${p.id}` }));
    }
    expect(screen.getByTestId("selected-count")).toHaveTextContent(
      String(MAX_COMPARE)
    );
    // clicking a selected one deselects it
    fireEvent.click(screen.getByRole("button", { name: "sel-1" }));
    expect(screen.getByTestId("selected-count")).toHaveTextContent(
      String(MAX_COMPARE - 1)
    );
  });

  it("imports legacy files and shows the summary notice", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse({ files_found: 5, imported: 3, skipped: 2 })
      )
    );
    renderManager();

    fireEvent.click(screen.getByRole("button", { name: "import" }));
    await waitFor(() => expect(refreshMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/profiles/import");
    expect(screen.getByTestId("notice")).toHaveTextContent(/3/);
  });

  it("joins 422 detail arrays into one error message", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse({ detail: [{ msg: "name required" }, { msg: "age bad" }] }, 422)
      )
    );
    renderManager();
    fireEvent.click(screen.getByRole("button", { name: "New Profile" }));
    fireEvent.click(screen.getByRole("button", { name: "save" }));

    await screen.findByTestId("form-error");
    expect(screen.getByTestId("form-error").textContent).toContain("name required");
    expect(screen.getByTestId("form-error").textContent).toContain("age bad");
    expect(refreshMock).not.toHaveBeenCalled();
  });
});
