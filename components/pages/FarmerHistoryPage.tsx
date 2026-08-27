"use client";

import { useCallback, useEffect, useState } from "react";

import { ErrorNotice, ErrorState, LoadingState } from "@/components/ui/AsyncState";
import { Icon } from "@/components/ui/Icons";
import { useFarmerSession } from "@/contexts/FarmerSessionContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { fetchFarmerWorkspace, upsertUser, searchFarmers, addFarm } from "@/lib/api";
import { MIN_FARMER_SEARCH_LENGTH } from "@/lib/constants";
import { toUserMessage } from "@/lib/errors";
import { useDebouncedValue } from "@/lib/hooks";
import type { AdvisoryRecord, FarmerWorkspace, FarmerSearchResult } from "@/lib/types";

export function FarmerHistoryPage() {
  const { t, language } = useLanguage();
  const { activeFarmer, setActiveFarmer, clearActiveFarmer } = useFarmerSession();
  const [activeTab, setActiveTab] = useState<"find" | "register" | "profile">(
    activeFarmer ? "profile" : "find"
  );
  const [workspace, setWorkspace] = useState<FarmerWorkspace | null>(null);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [workspaceReloadToken, setWorkspaceReloadToken] = useState(0);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<FarmerSearchResult[]>([]);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const debouncedSearchQuery = useDebouncedValue(searchQuery, 400);
  const trimmedSearchQuery = debouncedSearchQuery.trim();
  const isSearchQueryTooShort =
    trimmedSearchQuery.length > 0 && trimmedSearchQuery.length < MIN_FARMER_SEARCH_LENGTH;

  const [form, setForm] = useState({
    farmer_id: "",
    name: "",
    mobile: "",
    state: "",
    district: "",
    farm_name: "",
    village: "",
    acres: 1,
    primary_crop: "wheat",
    soil_type: "loam",
    irrigation_source: "Canal"
  });

  // Fall back to the search tab whenever the active farmer is cleared.
  useEffect(() => {
    if (!activeFarmer) {
      setActiveTab((tab) => (tab === "profile" ? "find" : tab));
    }
  }, [activeFarmer]);

  const farmerId = activeFarmer?.farmer_id ?? null;

  useEffect(() => {
    if (!farmerId) {
      setWorkspace(null);
      setWorkspaceError(null);
      setWorkspaceLoading(false);
      return;
    }

    let cancelled = false;
    setWorkspaceLoading(true);

    fetchFarmerWorkspace(farmerId)
      .then((data) => {
        if (cancelled) {
          return;
        }
        setWorkspace(data);
        setWorkspaceError(null);
        setForm((prev) => ({
          ...prev,
          farmer_id: data.profile.farmer_id,
          name: data.profile.name,
          mobile: data.profile.mobile,
          state: data.profile.state ?? "",
          district: data.profile.district ?? "",
          farm_name: data.farms[0]?.farm_name ?? prev.farm_name,
          village: data.farms[0]?.village ?? prev.village,
          acres: data.farms[0]?.acres ?? prev.acres,
          primary_crop: data.farms[0]?.primary_crop ?? prev.primary_crop,
          soil_type: data.farms[0]?.soil_type ?? prev.soil_type,
          irrigation_source: data.farms[0]?.irrigation_source ?? prev.irrigation_source
        }));
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setWorkspace(null);
          setWorkspaceError(toUserMessage(caught, t("feedback.loadFailed")));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setWorkspaceLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [farmerId, workspaceReloadToken, t]);

  function generateId() {
    const s = () => Math.random().toString(36).substring(2, 6).toUpperCase();
    return `REG-${s()}-${s()}`;
  }

  function handleCopy(id: string) {
    void navigator.clipboard.writeText(id).catch(() => undefined);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const runSearch = useCallback(
    async (term: string, signal?: { cancelled: boolean }) => {
      // The API rejects anything shorter with a 422, so never send it.
      if (term.length < MIN_FARMER_SEARCH_LENGTH) {
        setSearchResults([]);
        setSearchError(null);
        setHasSearched(false);
        return;
      }

      setBusy(true);
      setSearchError(null);
      try {
        const results = await searchFarmers(term);
        if (!signal?.cancelled) {
          setSearchResults(results);
          setHasSearched(true);
        }
      } catch (caught) {
        if (!signal?.cancelled) {
          setSearchResults([]);
          setHasSearched(true);
          setSearchError(toUserMessage(caught, t("feedback.searchFailed")));
        }
      } finally {
        if (!signal?.cancelled) {
          setBusy(false);
        }
      }
    },
    [t]
  );

  // Debounced auto-search: typing "R" or "Ra" never reaches the network.
  useEffect(() => {
    const signal = { cancelled: false };
    void runSearch(trimmedSearchQuery, signal);
    return () => {
      signal.cancelled = true;
    };
  }, [trimmedSearchQuery, runSearch]);

  async function handleSave() {
    setBusy(true);
    setSaveError(null);
    try {
      const finalId = form.farmer_id.trim() || generateId();

      const profile = await upsertUser({
        farmer_id: finalId,
        name: form.name,
        mobile: form.mobile,
        state: form.state,
        district: form.district,
        language
      });

      await addFarm({
        farmer_id: profile.farmer_id,
        mobile: profile.mobile,
        farm_name: form.farm_name,
        village: form.village,
        district: form.district,
        state: form.state,
        acres: form.acres,
        primary_crop: form.primary_crop,
        soil_type: form.soil_type,
        irrigation_source: form.irrigation_source
      });

      setActiveFarmer(profile);
      setActiveTab("profile");
    } catch (caught) {
      // Without this the rejection is unhandled and the spinner just stops.
      setSaveError(toUserMessage(caught, t("feedback.saveFailed")));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">{t("nav.history")}</h1>
        <p className="page-subtitle">
          Find your name or register once — your soil reports and advice history are saved.
        </p>
      </div>

      {/* Tabs Navigation */}
      <nav className="portal-tabs">
        <button
          type="button"
          className={`portal-tab-btn ${activeTab === "find" ? "active" : ""}`}
          onClick={() => setActiveTab("find")}
        >
          {t("common.search")}
        </button>
        <button
          type="button"
          className={`portal-tab-btn ${activeTab === "register" ? "active" : ""}`}
          onClick={() => setActiveTab("register")}
        >
          {t("farmer.createTitle")}
        </button>
        <button
          type="button"
          className={`portal-tab-btn ${activeTab === "profile" ? "active" : ""}`}
          disabled={!activeFarmer}
          onClick={() => setActiveTab("profile")}
        >
          {t("history.title")}
        </button>
      </nav>

      <section>
        {activeTab === "find" && (
          <article className="surface-card">
            <h3 className="section-title">{t("shell.searchFarmers")}</h3>
            <div className="search-panel-airy">
              <div>
                <label className="field-label" htmlFor="history-farmer-search">
                  {t("shell.searchPlaceholder")}
                </label>
                <div className="search-input-group">
                  <input
                    id="history-farmer-search"
                    className="field-input"
                    placeholder={t("shell.searchPlaceholder")}
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        void runSearch(searchQuery.trim());
                      }
                    }}
                  />
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => void runSearch(searchQuery.trim())}
                    disabled={busy || searchQuery.trim().length < MIN_FARMER_SEARCH_LENGTH}
                  >
                    <Icon name="search" size={20} />
                    {busy ? t("common.loading") : t("common.search")}
                  </button>
                </div>
                {isSearchQueryTooShort && (
                  <p className="hint-text">{t("feedback.minSearchLength")}</p>
                )}
              </div>

              {searchError && (
                <ErrorNotice message={searchError} onDismiss={() => setSearchError(null)} />
              )}

              {searchResults.length > 0 ? (
                <div className="search-results-list">
                  {searchResults.map((farmer: FarmerSearchResult) => {
                    const isActive = farmer.farmer_id === activeFarmer?.farmer_id;
                    const placeLine = [farmer.village, farmer.district]
                      .filter(Boolean)
                      .join(", ");
                    return (
                      <div
                        key={farmer.farmer_id}
                        className={`search-result-card ${isActive ? "active" : ""}`}
                      >
                        <div className="result-info">
                          <strong>{farmer.name}</strong>
                          {placeLine && <span style={{ fontWeight: 600 }}>{placeLine}</span>}
                          <span>
                            {farmer.farmer_id} · {farmer.mobile}
                          </span>
                        </div>
                        <button
                          type="button"
                          className="select-pill"
                          onClick={() => {
                            setActiveFarmer(farmer);
                            setActiveTab("profile");
                          }}
                          disabled={isActive}
                        >
                          {isActive ? t("common.activeFarmer") : "This is me"}
                        </button>
                      </div>
                    );
                  })}
                </div>
              ) : (
                hasSearched &&
                !busy &&
                !searchError && (
                  <div className="empty-state">
                    <Icon name="search" size={30} />
                    <p>{t("shell.noSearchResults")}</p>
                  </div>
                )
              )}
            </div>
          </article>
        )}

        {activeTab === "register" && (
          <article className="surface-card">
            <div style={{ marginBottom: "1.5rem" }}>
              <h3 className="section-title" style={{ marginBottom: "0.25rem" }}>
                {t("farmer.createTitle")}
              </h3>
              <p className="field-help" style={{ marginTop: 0 }}>
                {t("farmer.createBody")}
              </p>
            </div>

            <div className="airy-portal-grid">
              <div className="portal-form-group">
                <div className="form-header-with-icon">
                  <div className="crop-icon-wrapper" style={{ width: 48, height: 48 }}>
                    <Icon name="farmer" size={24} />
                  </div>
                  <h4 className="tips-title" style={{ marginBottom: 0 }}>
                    {t("history.profile")}
                  </h4>
                </div>

                <div className="form-stack">
                  <div>
                    <label className="field-label" htmlFor="reg-name">
                      {t("farmer.name")}
                    </label>
                    <input
                      id="reg-name"
                      className="field-input"
                      value={form.name}
                      onChange={(e) => setForm({ ...form, name: e.target.value })}
                      placeholder="e.g. Ramesh Kumar"
                    />
                  </div>
                  <div>
                    <label className="field-label" htmlFor="reg-mobile">
                      {t("farmer.mobile")}
                    </label>
                    <input
                      id="reg-mobile"
                      className="field-input"
                      inputMode="tel"
                      value={form.mobile}
                      onChange={(e) => setForm({ ...form, mobile: e.target.value })}
                      placeholder="e.g. 9876543210"
                    />
                    <p className="field-help">10 digits, without +91.</p>
                  </div>
                  <div className="grid-2-cols">
                    <div>
                      <label className="field-label" htmlFor="reg-state">
                        {t("farmer.state")}
                      </label>
                      <input
                        id="reg-state"
                        className="field-input"
                        value={form.state}
                        onChange={(e) => setForm({ ...form, state: e.target.value })}
                      />
                    </div>
                    <div>
                      <label className="field-label" htmlFor="reg-district">
                        {t("farmer.district")}
                      </label>
                      <input
                        id="reg-district"
                        className="field-input"
                        value={form.district}
                        onChange={(e) => setForm({ ...form, district: e.target.value })}
                      />
                    </div>
                  </div>
                </div>
              </div>

              <div className="portal-form-group">
                <div className="form-header-with-icon">
                  <div className="crop-icon-wrapper" style={{ width: 48, height: 48 }}>
                    <Icon name="tools" size={24} />
                  </div>
                  <h4 className="tips-title" style={{ marginBottom: 0 }}>
                    {t("history.farms")}
                  </h4>
                </div>

                <div className="form-stack">
                  <div>
                    <label className="field-label" htmlFor="reg-farm-name">
                      {t("farmer.farmName")}
                    </label>
                    <input
                      id="reg-farm-name"
                      className="field-input"
                      value={form.farm_name}
                      onChange={(e) => setForm({ ...form, farm_name: e.target.value })}
                      placeholder="What you call this field"
                    />
                  </div>
                  <div className="grid-2-cols">
                    <div>
                      <label className="field-label" htmlFor="reg-acres">
                        {t("farmer.farmSize")}
                      </label>
                      <input
                        id="reg-acres"
                        type="number"
                        className="field-input"
                        inputMode="decimal"
                        value={form.acres}
                        onChange={(e) => setForm({ ...form, acres: Number(e.target.value) })}
                      />
                    </div>
                    <div>
                      <label className="field-label" htmlFor="reg-crop">
                        {t("farmer.crop")}
                      </label>
                      <input
                        id="reg-crop"
                        className="field-input"
                        value={form.primary_crop}
                        onChange={(e) => setForm({ ...form, primary_crop: e.target.value })}
                      />
                    </div>
                  </div>
                  <div>
                    <label className="field-label" htmlFor="reg-village">
                      {t("farmer.village")}
                    </label>
                    <input
                      id="reg-village"
                      className="field-input"
                      value={form.village}
                      onChange={(e) => setForm({ ...form, village: e.target.value })}
                      placeholder="Village or block name"
                    />
                  </div>
                </div>
              </div>
            </div>

            {saveError && (
              <div style={{ marginTop: "1rem" }}>
                <ErrorNotice message={saveError} onDismiss={() => setSaveError(null)} />
              </div>
            )}

            <div
              style={{
                marginTop: "1.5rem",
                paddingTop: "1.25rem",
                borderTop: "1px solid var(--line)"
              }}
            >
              <button type="button" className="btn-primary" onClick={handleSave} disabled={busy}>
                {busy ? t("common.loading") : t("common.save")}
              </button>
            </div>
          </article>
        )}

        {activeTab === "profile" && activeFarmer && (
          <div className="portal-container">
            <aside className="portal-sidebar">
              <article className="surface-card">
                <h3 className="section-title">{t("common.activeFarmer")}</h3>

                <div className="id-badge-container relative" style={{ marginBottom: "1.25rem" }}>
                  <div style={{ display: "flex", flexDirection: "column" }}>
                    <span className="id-badge-label">{t("farmer.id")}</span>
                    <span className="id-value">{activeFarmer.farmer_id}</span>
                  </div>
                  <button
                    type="button"
                    className="copy-btn"
                    onClick={() => handleCopy(activeFarmer.farmer_id)}
                    aria-label={t("farmer.id")}
                  >
                    {copied ? <Icon name="check" size={20} /> : "Copy"}
                  </button>
                  {copied && <div className="success-toast">Copied</div>}
                </div>

                <div style={{ marginBottom: "1.25rem" }}>
                  <p className="farmer-name" style={{ fontSize: "1.35rem" }}>
                    {activeFarmer.name}
                  </p>
                  <p className="farmer-meta">
                    {activeFarmer.mobile}
                    {activeFarmer.district ? ` · ${activeFarmer.district}` : ""}
                  </p>
                </div>

                <div className="list-row">
                  <span className="stat-label">{t("dashboard.totalFarms")}</span>
                  <span className="stat-value" style={{ fontSize: "1.35rem" }}>
                    {workspace?.farms.length ?? 0}
                  </span>
                </div>
                <div className="list-row">
                  <span className="stat-label">{t("dashboard.savedRecords")}</span>
                  <span className="stat-value" style={{ fontSize: "1.35rem" }}>
                    {workspace?.advisories.length ?? 0}
                  </span>
                </div>

                <button
                  type="button"
                  className="btn-secondary w-full"
                  style={{ marginTop: "1rem" }}
                  onClick={() => clearActiveFarmer()}
                >
                  {t("shell.clearFarmer")}
                </button>
              </article>
            </aside>

            <main className="portal-main">
              <article className="surface-card">
                <h3 className="section-title">{t("history.advisories")}</h3>

                {workspaceLoading ? (
                  <LoadingState icon="history" />
                ) : workspaceError ? (
                  <ErrorState
                    message={workspaceError}
                    onRetry={() => setWorkspaceReloadToken((token) => token + 1)}
                  />
                ) : workspace?.advisories && workspace.advisories.length > 0 ? (
                  <div>
                    {workspace.advisories.map((item: AdvisoryRecord) => (
                      <div key={item.id} className="record-item">
                        <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                          <div
                            style={{
                              display: "flex",
                              alignItems: "center",
                              flexWrap: "wrap",
                              gap: "0.6rem"
                            }}
                          >
                            <span className="badge badge-success">
                              {item.module.toUpperCase()}
                            </span>
                            <p className="record-title">{item.summary}</p>
                          </div>
                          <p className="record-meta">
                            {new Date(item.created_at).toLocaleString()}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state">
                    <Icon name="history" size={30} />
                    <p>{t("history.noAdvice")}</p>
                  </div>
                )}
              </article>
            </main>
          </div>
        )}
      </section>
    </div>
  );
}
