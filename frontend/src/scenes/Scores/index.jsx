import { API_BASE_URL } from "../../api";
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
    Alert,
    Box,
    Button,
    CircularProgress,
    Stack,
    Typography,
} from "@mui/material";
import FileDownloadOutlined from "@mui/icons-material/FileDownloadOutlined";
import * as XLSX from "xlsx";
import Header from "../../components/Header";
import ScoreHistoryChart from "../../components/ScoreHistoryChart";

const API_URL = API_BASE_URL;
const POLL_INTERVAL = 1000;
const HISTORY_WINDOW_MS = 10 * 60 * 1000;
// À un intervalle d'environ une seconde, 601 points couvrent 10 minutes inclusives.
const MAX_POINTS = Math.floor(HISTORY_WINDOW_MS / POLL_INTERVAL) + 1;
const BAND_KEYS = ["2G", "5G", "6G"];

function getDeviceId(device, index = 0) {
    return String(device?._scoreId || device?.mac || device?.hostname || `device_${index}`);
}

function getScoreKey(deviceId) {
    return `score_${encodeURIComponent(String(deviceId))}`;
}

function getBandKey(deviceId) {
    return `band_${encodeURIComponent(String(deviceId))}`;
}

function getBandScoreKey(deviceId, band) {
    return `band_score_${encodeURIComponent(String(deviceId))}_${encodeURIComponent(String(band))}`;
}

function getScoreForBand(device, band) {
    const value = device?.scores?.[band];
    if (value === null || value === undefined || value === "") return null;
    const score = Number(value);
    return Number.isFinite(score) ? score : null;
}

function getCurrentScore(device) {
    const value = device?.scores?.[device?.current_band];

    if (value === null || value === undefined || value === "") {
    }

    const score = Number(value);
    return Number.isFinite(score) ? score : null;
}

function formatTime(timestamp) {
    const date = new Date(Number(timestamp));
    if (Number.isNaN(date.getTime())) return "—";

    return date.toLocaleTimeString("fr-FR", {
        hour: "2-digit",
        minute: "2-digit"
    });
}

function formatDate(timestamp) {
    const date = new Date(Number(timestamp));
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleDateString("fr-FR");
}

function getDeviceLabel(device, index = 0) {
    const id = getDeviceId(device, index);
    if (device?.hostname && device?.mac) {
        return `${device.hostname} (${device.mac})`;
    }
    return device?.hostname || device?.mac || id;
}

export default function Scores() {
    const [devices, setDevices] = useState([]);
    const [history, setHistory] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [exportError, setExportError] = useState("");
    const [now, setNow] = useState(() => Date.now());

    // Conserve les appareils déjà vus, même s'ils disparaissent temporairement
    // d'une réponse de l'API.
    const knownDevicesRef = useRef(new Map());

    // Le graphique et l'export restent strictement limités à la fenêtre des 10 minutes.
    const visibleHistory = useMemo(
        () => history.filter((point) => Number(point.timestamp) >= now - HISTORY_WINDOW_MS),
        [history, now]
    );

    useEffect(() => {
        const clock = window.setInterval(() => setNow(Date.now()), 1000);
        return () => window.clearInterval(clock);
    }, []);

    useEffect(() => {
        let active = true;
        let timer = null;
        let requestInProgress = false;

        const loadScores = async () => {
            if (!active || requestInProgress) return;
            requestInProgress = true;

            try {
                const response = await fetch(`${API_URL}/api/steering`, {
                    method: "GET",
                    cache: "no-store",
                    headers: { Accept: "application/json" },
                });

                if (!response.ok) {
                    throw new Error(`Erreur HTTP ${response.status}`);
                }

                const payload = await response.json();
                if (!active) return;

                const currentDevices = Array.isArray(payload?.devices)
                    ? payload.devices
                    : [];
                const currentIds = new Set();

                currentDevices.forEach((device, index) => {
                    const id = getDeviceId(device, index);
                    currentIds.add(id);
                    knownDevicesRef.current.set(id, {
                        ...device,
                        _scoreId: id,
                    });
                });

                const allKnownDevices = Array.from(knownDevicesRef.current.values());
                const timestamp = Date.now();
                const point = {
                    timestamp,
                    time: formatTime(timestamp),
                };

                allKnownDevices.forEach((device) => {
                    const id = device._scoreId;
                    const isPresent = currentIds.has(id);
                    point[getScoreKey(id)] = isPresent ? getCurrentScore(device) : null;
                    // Enregistre la bande courante et les scores de toutes les bandes à chaque mesure.
                    point[getBandKey(id)] = isPresent ? (device.current_band || "") : "";
                    BAND_KEYS.forEach((band) => {
                        point[getBandScoreKey(id, band)] = isPresent
                            ? getScoreForBand(device, band)
                            : null;
                    });
                });

                setDevices(allKnownDevices);
                setHistory((previous) =>
                    [...previous, point]
                        .filter((item) => Number(item.timestamp) >= timestamp - HISTORY_WINDOW_MS)
                        .slice(-MAX_POINTS)
                );
                setNow(timestamp);
                setError("");
            } catch (err) {
                if (active) {
                    setError(err?.message || "Impossible de récupérer les scores.");
                }
            } finally {
                requestInProgress = false;
                if (active) {
                    setLoading(false);
                    // Le prochain appel commence après la fin du précédent.
                    timer = window.setTimeout(loadScores, POLL_INTERVAL);
                }
            }
        };

        loadScores();

        return () => {
            active = false;
            if (timer !== null) window.clearTimeout(timer);
        };
    }, []);

    const exportExcel = () => {
        if (visibleHistory.length === 0 || devices.length === 0) return;

        try {
            const exportedDevices = devices.map((device, index) => {
                const id = getDeviceId(device, index);
                return {
                    id,
                    device,
                    label: getDeviceLabel(device, index),
                    scoreKey: getScoreKey(id),
                    bandKey: getBandKey(id),
                };
            });

            // Feuille 1 : format détaillé, idéal pour filtrer / analyser dans Excel.
            const detailRows = [[
                "Date",
                "Heure",
                "Horodatage ISO",
                "Identifiant appareil",
                "Nom appareil",
                "Adresse MAC",
                "Bande courante",
                "Score courant",
                "Score 2G",
                "Score 5G",
                "Score 6G",
            ]];

            visibleHistory.forEach((point) => {
                exportedDevices.forEach(({ id, device }) => {
                    const rawScore = point?.[getScoreKey(id)];
                    const numericScore = rawScore === null || rawScore === undefined || rawScore === ""
                        ? null
                        : Number(rawScore);
                    const score = Number.isFinite(numericScore) ? numericScore : "";
                    const timestamp = Number(point.timestamp);

                    const bandScores = BAND_KEYS.map((band) => {
                        const value = point?.[getBandScoreKey(id, band)];
                        return value === null || value === undefined || value === "" || !Number.isFinite(Number(value))
                            ? ""
                            : Number(value);
                    });

                    detailRows.push([
                        formatDate(timestamp),
                        point.time || formatTime(timestamp),
                        new Date(timestamp).toISOString(),
                        id,
                        device?.hostname || "",
                        device?.mac || "",
                        point?.[getBandKey(id)] || "",
                        score,
                        ...bandScores,
                    ]);
                });
            });

            const detailSheet = XLSX.utils.aoa_to_sheet(detailRows);
            detailSheet["!cols"] = [
                { wch: 12 },
                { wch: 12 },
                { wch: 25 },
                { wch: 24 },
                { wch: 24 },
                { wch: 20 },
                { wch: 14 },
                { wch: 12 },
                { wch: 12 },
                { wch: 12 },
                { wch: 12 },
            ];
            if (detailRows.length > 1) {
                detailSheet["!autofilter"] = {
                    ref: XLSX.utils.encode_range({
                        s: { r: 0, c: 0 },
                        e: { r: detailRows.length - 1, c: detailRows[0].length - 1 },
                    }),
                };
            }

            // Feuille 2 : une ligne par instant, avec les scores de tous les appareils.
            const timelineHeaders = ["Date", "Heure", "Horodatage ISO"];
            exportedDevices.forEach(({ label }) => {
                timelineHeaders.push(
                    `${label} — Score courant`,
                    `${label} — Bande courante`,
                    ...BAND_KEYS.map((band) => `${label} — Score ${band}`)
                );
            });

            const timelineRows = [timelineHeaders];
            visibleHistory.forEach((point) => {
                const timestamp = Number(point.timestamp);
                const row = [
                    formatDate(timestamp),
                    point.time || formatTime(timestamp),
                    new Date(timestamp).toISOString(),
                ];

                exportedDevices.forEach(({ id, scoreKey, bandKey }) => {
                    const rawScore = point?.[scoreKey];
                    const numericScore = rawScore === null || rawScore === undefined || rawScore === ""
                        ? null
                        : Number(rawScore);
                    row.push(Number.isFinite(numericScore) ? numericScore : "");
                    row.push(point?.[bandKey] || "");
                    BAND_KEYS.forEach((band) => {
                        const value = point?.[getBandScoreKey(id, band)];
                        const numericValue = value === null || value === undefined || value === ""
                            ? null
                            : Number(value);
                        row.push(Number.isFinite(numericValue) ? numericValue : "");
                    });
                });
                timelineRows.push(row);
            });

            const timelineSheet = XLSX.utils.aoa_to_sheet(timelineRows);
            timelineSheet["!cols"] = [
                { wch: 12 },
                { wch: 12 },
                { wch: 25 },
                ...exportedDevices.flatMap(() => [
                    { wch: 24 },
                    { wch: 16 },
                    { wch: 12 },
                    { wch: 12 },
                    { wch: 12 },
                ]),
            ];
            if (timelineRows.length > 1) {
                timelineSheet["!autofilter"] = {
                    ref: XLSX.utils.encode_range({
                        s: { r: 0, c: 0 },
                        e: { r: timelineRows.length - 1, c: timelineHeaders.length - 1 },
                    }),
                };
            }

            const workbook = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(workbook, detailSheet, "Historique detaille");
            XLSX.utils.book_append_sheet(workbook, timelineSheet, "Vue temporelle");

            const fileTimestamp = new Date().toISOString().replace(/[:.]/g, "-");
            XLSX.writeFile(workbook, `scores_wifi_10_minutes_${fileTimestamp}.xlsx`);
            setExportError("");
        } catch (err) {
            console.error("Échec de l'export Excel des scores :", err);
            setExportError("L'export Excel a échoué. Vérifie que la dépendance xlsx est installée.");
        }
    };

    return (
        <>
            <Header />

            <Box sx={{ p: { xs: 2, md: 3 } }}>
                <Stack
                    direction={{ xs: "column", sm: "row" }}
                    justifyContent="space-between"
                    alignItems={{ xs: "flex-start", sm: "center" }}
                    spacing={2}
                    sx={{ mb: 1 }}
                >
                    <Box>
                        <Typography variant="h4" fontWeight={800}>
                            Multi-Metrics Scores 
                        </Typography>
                        <Typography color="text.secondary" sx={{ mt: 0.5 }}>
                            Scores evolution of all devices.
                        </Typography>
                    </Box>

                    <Button
                        variant="contained"
                        color="success"
                        startIcon={<FileDownloadOutlined />}
                        onClick={exportExcel}
                        disabled={visibleHistory.length === 0 || devices.length === 0}
                        sx={{ fontWeight: 700, whiteSpace: "nowrap" }}
                    >
                        Export  Excel
                    </Button>
                </Stack>

                <Typography color="text.secondary" mb={3}>
A measurement is collected approximately every second. The history is stored in memory for the duration of the session.
                </Typography>

                {error && (
                    <Alert severity="error" sx={{ mb: 2 }}>
                        {error}. Vérifie que le backend est démarré et que l'API
                        {` ${API_URL}/api/steering `}est accessible. Les mesures déjà collectées sont conservées.
                    </Alert>
                )}

                {exportError && (
                    <Alert severity="error" sx={{ mb: 2 }} onClose={() => setExportError("")}>
                        {exportError}
                    </Alert>
                )}

                {loading ? (
                    <Stack alignItems="center" spacing={2} sx={{ py: 8 }}>
                        <CircularProgress />
                        <Typography color="text.secondary">Loading of  scores...</Typography>
                    </Stack>
                ) : (
                    <ScoreHistoryChart history={visibleHistory} devices={devices} />
                )}
            </Box>
        </>
    );
}
