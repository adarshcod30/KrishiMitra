"use client";

import { useCallback, useEffect, useState } from "react";
import { ErrorNotice, ErrorState, LoadingState } from "@/components/ui/AsyncState";
import { PageHeader } from "@/components/ui/PageHeader";
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
      <PageHeader
        eyebrow={t("nav.history")}
        title="Farmer Portal"
        description="A unified agricultural identity and record management system."
      />

      <div className="portal-container mt-8">
        <main className="w-full">
          {/* Tabs Navigation */}
          <nav className="portal-tabs">
            <button
              className={`portal-tab-btn ${activeTab === "find" ? "active" : ""}`}
              onClick={() => setActiveTab("find")}
            >
              {t("common.search")}
            </button>
            <button
              className={`portal-tab-btn ${activeTab === "register" ? "active" : ""}`}
              onClick={() => setActiveTab("register")}
            >
              {t("farmer.createTitle")}
            </button>
            <button
              className={`portal-tab-btn ${activeTab === "profile" ? "active" : ""}`}
              disabled={!activeFarmer}
              onClick={() => setActiveTab("profile")}
            >
              {t("history.title")}
            </button>
          </nav>

          <section className="portal-tab-content">
            {activeTab === "find" && (
              <article className="surface-card">
                <h3 className="section-title mb-6">{t("shell.searchFarmers")}</h3>
                <div className="search-panel-airy">
                  <div className="field">
                    <span>{t("common.search")}</span>
                    <div className="search-input-group">
                      <input
                        className="airy-input"
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
                        className="primary-btn"
                        onClick={() => void runSearch(searchQuery.trim())}
                        disabled={busy || searchQuery.trim().length < MIN_FARMER_SEARCH_LENGTH}
                      >
                        {busy ? "..." : t("common.search")}
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
                    <div className="search-results-list mt-6">
                      {searchResults.map((farmer: FarmerSearchResult) => (
                        <div 
                          key={farmer.farmer_id} 
                          className={`search-result-card ${farmer.farmer_id === activeFarmer?.farmer_id ? 'active' : ''}`}
                        >
                          <div className="result-info">
                            <div className="flex items-center gap-2">
                              <strong>{farmer.name}</strong>
                              {farmer.farmer_id === activeFarmer?.farmer_id && (
                                <span className="badge badge-accent text-[10px] py-0 px-1">Active</span>
                              )}
                            </div>
                            <span>{farmer.farmer_id} • {farmer.mobile}</span>
                            {farmer.village && <span className="text-xs text-muted block">{farmer.village}, {farmer.district}</span>}
                          </div>
                          <button
                            className="select-pill"
                            onClick={() => {
                              setActiveFarmer(farmer);
                              setActiveTab("profile");
                            }}
                            disabled={farmer.farmer_id === activeFarmer?.farmer_id}
                          >
                            {farmer.farmer_id === activeFarmer?.farmer_id ? t("common.activeFarmer") : t("common.select")}
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    hasSearched && !busy && !searchError && (
                      <div className="empty-state-airy mt-6">
                        <div className="text-2xl mb-2">🔍</div>
                        <p>{t("shell.noSearchResults")}</p>
                      </div>
                    )
                  )}
                </div>
              </article>
            )}

            {activeTab === "register" && (
              <article className="surface-card">
                <div className="flex justify-between items-center mb-8">
                  <div>
                    <h3 className="section-title mb-1">{t("farmer.createTitle")}</h3>
                    <p className="text-sm text-muted">{t("farmer.createBody")}</p>
                  </div>
                  <div className="badge badge-accent">Secure Portal</div>
                </div>

                <div className="registration-flow">
                  <div className="airy-portal-grid">
                    <div className="portal-form-group">
                      <div className="form-header-with-icon">
                        <div className="crop-icon-wrapper" style={{ fontSize: '1.2rem', padding: '0.8rem' }}>👤</div>
                        <h4 className="tips-title mb-0">{t("history.profile")}</h4>
                      </div>
                      
                      <div className="form-stack space-y-4">
                        <label className="field">
                          <span>{t("farmer.name")}</span>
                          <input
                            className="airy-input"
                            value={form.name}
                            onChange={(e) => setForm({ ...form, name: e.target.value })}
                            placeholder="Full Name (e.g. Adarsh Kumar)"
                            style={{ padding: '1.2rem' }}
                          />
                        </label>
                        <label className="field">
                          <span>{t("farmer.mobile")}</span>
                          <input
                            className="airy-input"
                            value={form.mobile}
                            onChange={(e) => setForm({ ...form, mobile: e.target.value })}
                            placeholder="10-digit primary mobile"
                            style={{ padding: '1.2rem' }}
                          />
                        </label>
                        <div className="grid grid-cols-2 gap-6">
                          <label className="field">
                            <span>{t("farmer.state")}</span>
                            <input
                              className="airy-input"
                              value={form.state}
                              onChange={(e) => setForm({ ...form, state: e.target.value })}
                              style={{ padding: '1.2rem' }}
                            />
                          </label>
                          <label className="field">
                            <span>{t("farmer.district")}</span>
                            <input
                              className="airy-input"
                              value={form.district}
                              onChange={(e) => setForm({ ...form, district: e.target.value })}
                              style={{ padding: '1.2rem' }}
                            />
                          </label>
                        </div>
                      </div>
                    </div>

                    <div className="portal-form-group">
                      <div className="form-header-with-icon">
                        <div className="crop-icon-wrapper" style={{ fontSize: '1.2rem', padding: '0.8rem' }}>🚜</div>
                        <h4 className="tips-title mb-0">{t("history.farms")}</h4>
                      </div>

                      <div className="form-stack space-y-4">
                        <label className="field">
                          <span>{t("farmer.farmName")}</span>
                          <input
                            className="airy-input"
                            value={form.farm_name}
                            onChange={(e) => setForm({ ...form, farm_name: e.target.value })}
                            placeholder="e.g. West Highlands Farm"
                            style={{ padding: '1.2rem' }}
                          />
                        </label>
                        <div className="grid grid-cols-2 gap-6">
                          <label className="field">
                            <span>{t("farmer.farmSize")} (Acres)</span>
                            <input
                              type="number"
                              className="airy-input"
                              value={form.acres}
                              onChange={(e) => setForm({ ...form, acres: Number(e.target.value) })}
                              style={{ padding: '1.2rem' }}
                            />
                          </label>
                          <label className="field">
                            <span>{t("farmer.crop")}</span>
                            <input
                              className="airy-input"
                              value={form.primary_crop}
                              onChange={(e) => setForm({ ...form, primary_crop: e.target.value })}
                              style={{ padding: '1.2rem' }}
                            />
                          </label>
                        </div>
                        <label className="field">
                          <span>{t("farmer.village")} / Location</span>
                          <input
                            className="airy-input"
                            value={form.village}
                            onChange={(e) => setForm({ ...form, village: e.target.value })}
                            placeholder="Village or Block name"
                            style={{ padding: '1.2rem' }}
                          />
                        </label>
                      </div>
                    </div>
                  </div>

                  {saveError && (
                    <ErrorNotice message={saveError} onDismiss={() => setSaveError(null)} />
                  )}

                  <div className="mt-12 pt-8 border-t border-line flex justify-end">
                    <button type="button" className="primary-btn px-16 py-4 text-lg" onClick={handleSave} disabled={busy}>
                      {busy ? t("common.loading") : t("common.save")}
                    </button>
                  </div>
                </div>
              </article>
            )}

            {activeTab === "profile" && activeFarmer && (
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <aside className="lg:col-span-1">
                  <article className="surface-card">
                    <h3 className="section-title mb-6">{t("common.activeFarmer")}</h3>
                    <div className="active-profile-summary">
                      <div className="id-badge-container mb-6">
                        <div className="flex flex-col">
                          <span className="id-badge-label">{t("farmer.id")}</span>
                          <span className="id-value">{activeFarmer.farmer_id}</span>
                        </div>
                        <button className="copy-btn" onClick={() => handleCopy(activeFarmer.farmer_id)}>
                          {copied ? "✓" : "❐"}
                        </button>
                        {copied && <div className="success-toast">Copied!</div>}
                      </div>

                      <div className="profile-brief mb-6">
                        <p className="farmer-name text-2xl mb-1">{activeFarmer.name}</p>
                        <p className="text-muted">{activeFarmer.mobile} • {activeFarmer.district}</p>
                      </div>

                      <div className="flex gap-2">
                        <button className="ghost-btn w-full" onClick={() => clearActiveFarmer()}>
                          {t("shell.clearFarmer")}
                        </button>
                      </div>
                    </div>
                  </article>

                  <article className="surface-card bg-brand-subtle mt-6">
                    <h4 className="font-bold text-brand mb-4">{t("dashboard.quickInsights")}</h4>
                    <div className="flex justify-between py-2 border-b border-brand border-opacity-10">
                      <span className="text-sm">{t("dashboard.totalFarms")}</span>
                      <strong>{workspace?.farms.length ?? 0}</strong>
                    </div>
                    <div className="flex justify-between py-2">
                      <span className="text-sm">{t("dashboard.savedRecords")}</span>
                      <strong>{workspace?.advisories.length ?? 0}</strong>
                    </div>
                  </article>
                </aside>

                <main className="lg:col-span-2 space-y-6">
                  <article className="surface-card min-h-[400px]">
                    <div className="flex justify-between items-center mb-8">
                      <h3 className="section-title mb-0">{t("history.advisories")}</h3>
                      <div className="badge badge-brand">LIVE DATA</div>
                    </div>

                    {workspaceLoading ? (
                      <LoadingState icon="👤" />
                    ) : workspaceError ? (
                      <ErrorState
                        message={workspaceError}
                        onRetry={() => setWorkspaceReloadToken((token) => token + 1)}
                      />
                    ) : workspace?.advisories && workspace.advisories.length > 0 ? (
                      <div className="records-list">
                        {workspace.advisories.map((item: AdvisoryRecord) => (
                          <div key={item.id} className="record-item hover:bg-slate-50 transition-colors">
                            <div className="record-info">
                              <div className="flex items-center gap-3">
                                <span className="badge badge-accent text-[10px]">
                                  {item.module.toUpperCase()}
                                </span>
                                <p className="record-title">{item.summary}</p>
                              </div>
                              <p className="text-xs text-muted mt-2 ml-[64px]">
                                {new Date(item.created_at).toLocaleString()}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-center py-20 bg-subtle rounded-xl border-2 border-dashed border-line-strong">
                        <p className="text-2xl mb-2">🌾</p>
                        <p className="muted-copy">No advisory records found.</p>
                      </div>
                    )}
                  </article>
                </main>
              </div>
            )}
          </section>
        </main>
      </div>
    </div>
  );
}
