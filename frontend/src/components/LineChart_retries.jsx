import { API_BASE_URL } from "../api";
import { useEffect, useState } from "react";
import {
    Box,
    FormControl,
    InputLabel,
    Select,
    MenuItem,
    Button,
    Typography,
} from "@mui/material";

import FileDownloadIcon from "@mui/icons-material/FileDownload";

import {
    ResponsiveContainer,
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
} from "recharts";

import * as XLSX from "xlsx";

const API_URL = `${API_BASE_URL}/api/retransmissions`;
const MAX_POINTS = 5000;

const COLORS = [
    "#8884d8",
    "#82ca9d",
    "#ffc658",
    "#ff7300",
    "#0088FE",
    "#00C49F",
    "#FFBB28",
    "#FF8042",
    "#a4de6c",
    "#d0ed57",
];

const DASH_STYLES = [
    "0",
    "5 5",
    "3 3",
    "8 3",
    "2 2",
    "10 5",
];

const LineChartRetries = () => {
    const [measurements, setMeasurements] = useState([]);
    const [stations, setStations] = useState([]);
    const [selectedStation, setSelectedStation] = useState("all");
    const [hiddenLines, setHiddenLines] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    // Récupération des mesures toutes les 2 secondes
    useEffect(() => {
        let mounted = true;

        const fetchMeasurements = async () => {
            try {
                const response = await fetch(API_URL);

                if (!response.ok) {
                    throw new Error("Error while retrieving measurements");
                }

                const result = await response.json();

                if (!mounted) return;

                const newMeasurements = result.measurements || [];

                setMeasurements((previous) => {
                    const merged = [...previous];

                    newMeasurements.forEach((item) => {
                        const exists = merged.some(
                            (old) =>
                                old.timestamp === item.timestamp &&
                                old.mac === item.mac &&
                                old.interface === item.interface
                        );

                        if (!exists) {
                            merged.push(item);
                        }
                    });

                    return merged.slice(-MAX_POINTS);
                });

                setError(null);
                setLoading(false);
            } catch (err) {
                console.error("Retransmissions errors:", err);

                if (mounted) {
                    setError(err.message);
                    setLoading(false);
                }
            }
        };

        fetchMeasurements();

        const interval = setInterval(fetchMeasurements, 2000);

        return () => {
            mounted = false;
            clearInterval(interval);
        };
    }, []);

    // Construction de la liste des stations
    useEffect(() => {
        const uniqueStations = [
            ...new Set(
                measurements.map(
                    (item) => `${item.mac} | ${item.interface}`
                )
            ),
        ];

        setStations(uniqueStations);
    }, [measurements]);

    // Export Excel
    const exportToExcel = () => {
        if (measurements.length === 0) {
            alert("No retransmission measurements to export.");
            return;
        }

        const excelData = measurements.map((item) => {
            const timestamp = Number(item.timestamp);
            const milliseconds =
                timestamp < 1e12 ? timestamp * 1000 : timestamp;

            const date = new Date(milliseconds);

            return {
                "Date et heure":
                    Number.isFinite(timestamp) &&
                    !Number.isNaN(date.getTime())
                        ? date.toLocaleString("fr-FR")
                        : "",

                "Station MAC": item.mac ?? "",
                "Interface Wi-Fi": item.interface ?? "",
                "Bande Wi-Fi": item.band ?? "",
                "Paquets transmis": item.tx_packets ?? 0,
                Retransmissions: item.tx_retries ?? 0,
                "Paquets échoués": item.tx_failed ?? 0,
                "Durée transmission (us)": item.tx_duration ?? 0,
                "Retry Rate (%)":
                    item.retry_rate == null
                        ? ""
                        : Number(item.retry_rate),
                "Intervalle (s)": item.elapsed ?? "",
            };
        });

        const worksheet = XLSX.utils.json_to_sheet(excelData);

        worksheet["!cols"] = [
            { wch: 22 },
            { wch: 22 },
            { wch: 20 },
            { wch: 15 },
            { wch: 18 },
            { wch: 18 },
            { wch: 18 },
            { wch: 25 },
            { wch: 18 },
            { wch: 15 },
        ];

        const workbook = XLSX.utils.book_new();

        XLSX.utils.book_append_sheet(
            workbook,
            worksheet,
            "Retransmissions"
        );

        const now = new Date();

        const dateSuffix = [
            now.getFullYear(),
            String(now.getMonth() + 1).padStart(2, "0"),
            String(now.getDate()).padStart(2, "0"),
        ].join("-");

        const timeSuffix = [
            String(now.getHours()).padStart(2, "0"),
            String(now.getMinutes()).padStart(2, "0"),
            String(now.getSeconds()).padStart(2, "0"),
        ].join("-");

        XLSX.writeFile(
            workbook,
            `mesures_Retransmissions_${dateSuffix}_${timeSuffix}.xlsx`
        );
    };

    // Filtrage des mesures selon la station sélectionnée
    const filteredMeasurements =
        selectedStation === "all"
            ? measurements
            : measurements.filter(
                  (item) =>
                      `${item.mac} | ${item.interface}` === selectedStation
              );

    // Construction des clés des lignes
    const lineKeys = [
        ...new Set(
            filteredMeasurements.map(
                (item) => `${item.mac} | ${item.interface}`
            )
        ),
    ];

    // Transformation des données pour Recharts
    const chartDataMap = {};

    filteredMeasurements.forEach((item) => {
        const timestamp = Number(item.timestamp);

        const milliseconds =
            timestamp < 1e12 ? timestamp * 1000 : timestamp;

        const key = milliseconds;

        if (!chartDataMap[key]) {
            chartDataMap[key] = {
                timestamp: milliseconds,
                time: new Date(milliseconds).toLocaleTimeString("fr-FR"),
            };
        }

        const lineKey = `${item.mac} | ${item.interface}`;

        chartDataMap[key][lineKey] =
            item.retry_rate == null
                ? null
                : Number(item.retry_rate);
    });

    const chartData = Object.values(chartDataMap).sort(
        (a, b) => a.timestamp - b.timestamp
    );

    // Gestion de la légende interactive
    const handleLegendClick = (entry) => {
        const lineName = entry.value;

        setHiddenLines((previous) =>
            previous.includes(lineName)
                ? previous.filter((name) => name !== lineName)
                : [...previous, lineName]
        );
    };

    // Tooltip personnalisé
    const CustomTooltip = ({ active, payload, label }) => {
        if (!active || !payload || payload.length === 0) {
            return null;
        }

        return (
            <Box
                sx={{
                    backgroundColor: "#1f2a40",
                    padding: "12px",
                    border: "1px solid #555",
                    borderRadius: "5px",
                }}
            >
                <Typography color="#ffffff" fontWeight="bold">
                    {new Date(label).toLocaleString("fr-FR")}
                </Typography>

                {payload.map((entry, index) => (
                    <Typography
                        key={index}
                        sx={{
                            color: entry.color,
                            fontSize: "13px",
                        }}
                    >
                        {entry.name}:{" "}
                        {entry.value == null
                            ? "N/A"
                            : `${Number(entry.value).toFixed(2)} %`}
                    </Typography>
                ))}
            </Box>
        );
    };

    // Statistiques globales
    const validRates = filteredMeasurements
        .map((item) => item.retry_rate)
        .filter((value) => value != null && Number.isFinite(Number(value)))
        .map(Number);

    const averageRate =
        validRates.length > 0
            ? validRates.reduce((sum, value) => sum + value, 0) /
              validRates.length
            : null;

    const maxRate =
        validRates.length > 0
            ? Math.max(...validRates)
            : null;

    if (loading) {
        return (
            <Box p="20px">
                <Typography>Chargement des mesures de retransmission...</Typography>
            </Box>
        );
    }

    return (
        <Box width="100%" height="100%" p="10px">
            {/* En-tête et filtres */}
            <Box
                display="flex"
                justifyContent="space-between"
                alignItems="center"
                flexWrap="wrap"
                gap="15px"
                mb="20px"
            >
                <Box>
                    <Typography variant="h5" fontWeight="bold">
                       
                    </Typography>

                    <Typography variant="body2" color="text.secondary">
          
                    </Typography>
                </Box>

                <Box
                    display="flex"
                    alignItems="center"
                    flexWrap="wrap"
                    gap="10px"
                >
                    <FormControl size="small" sx={{ minWidth: 220 }}>
                        <InputLabel>Wi-Fi Station</InputLabel>

                        <Select
                            value={selectedStation}
                            label="Wi-Fi Station"
                            onChange={(event) =>
                                setSelectedStation(event.target.value)
                            }
                        >
                            <MenuItem value="all">
                                All stations
                            </MenuItem>

                            {stations.map((station) => (
                                <MenuItem
                                    key={station}
                                    value={station}
                                >
                                    {station}
                                </MenuItem>
                            ))}
                        </Select>
                    </FormControl>

                    <Button
                        variant="contained"
                        color="success"
                        startIcon={<FileDownloadIcon />}
                        onClick={exportToExcel}
                        disabled={measurements.length === 0}
                    >
                        Export to Excel
                    </Button>
                </Box>
            </Box>

            {/* Message d'erreur */}
            {error && (
                <Typography color="error" mb="10px">
                    Erreur : {error}
                </Typography>
            )}

            {/* Statistiques */}
            <Box
                display="flex"
                gap="30px"
                flexWrap="wrap"
                mb="15px"
            >
                <Box>
                    <Typography variant="body2" color="text.secondary">
                        Number of mesures
                    </Typography>

                    <Typography variant="h6">
                        {filteredMeasurements.length}
                    </Typography>
                </Box>

                <Box>
                    <Typography variant="body2" color="text.secondary">
                        Average Retry Ratio 
                    </Typography>

                    <Typography variant="h6">
                        {averageRate == null
                            ? "N/A"
                            : `${averageRate.toFixed(2)} %`}
                    </Typography>
                </Box>

                <Box>
                    <Typography variant="body2" color="text.secondary">
                        Maximum Retry Ratio 
                    </Typography>

                    <Typography variant="h6">
                        {maxRate == null
                            ? "N/A"
                            : `${maxRate.toFixed(2)} %`}
                    </Typography>
                </Box>
            </Box>

            {/* Graphique */}
            <Box width="100%" height="65vh">
                {chartData.length === 0 ? (
                    <Box
                        height="100%"
                        display="flex"
                        alignItems="center"
                        justifyContent="center"
                    >
                        <Typography color="text.secondary">
                          No measurements available at the moment.
                        </Typography>
                    </Box>
                ) : (
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart
                            data={chartData}
                            margin={{
                                top: 20,
                                right: 30,
                                left: 20,
                                bottom: 20,
                            }}
                        >
                            <CartesianGrid
                                strokeDasharray="3 3"
                                stroke="#888"
                                opacity={0.3}
                            />

    
                            <XAxis
				    dataKey="timestamp"
				    type="number"
				    domain={["dataMin", "dataMax"]}
				    scale="time"
				    tickFormatter={(value) =>
					new Date(value).toLocaleTimeString("fr-FR", {
					    hour: "2-digit",
					    minute: "2-digit",
					    hour12: false,
					})
				    }
				    tick={{ fontSize: 12 }}
				    minTickGap={30}
			    />

                            <YAxis
                                tickCount={8}
                                tick={{ fontSize: 12 }}
                                tickFormatter={(value) =>
                                    `${Number(value).toFixed(0)} %`
                                }
                                domain={[0, 200]}
                                allowDataOverflow={true}
                                label={{
                                    value: "Retry Ratio (%)",
                                    angle: -90,
                                    position: "insideLeft",
                                }}
                            />
		
                            <Tooltip content={<CustomTooltip />} />

                            <Legend
                                onClick={handleLegendClick}
                                wrapperStyle={{
                                    cursor: "pointer",
                                    paddingTop: "15px",
                                }}
                            />

                            {lineKeys.map((lineKey, index) => (
                                <Line
                                    key={lineKey}
                                    type="monotone"
                                    dataKey={lineKey}
                                    name={lineKey}
                                    stroke={
                                        COLORS[index % COLORS.length]
                                    }
                                    strokeDasharray={
                                        DASH_STYLES[
                                            index % DASH_STYLES.length
                                        ]
                                    }
                                    strokeWidth={2}
                                    dot={false}
                                    connectNulls={false}
                                    hide={hiddenLines.includes(lineKey)}
                                    isAnimationActive={false}
                                />
                            ))}
                        </LineChart>
                    </ResponsiveContainer>
                )}
            </Box>

            <Typography
                variant="caption"
                color="text.secondary"
                display="block"
                mt="10px"
            >
                Retry Ratio = number of retransmissions / number of packets transmitted
     × 100. 
            </Typography>
        </Box>
    );
};

export default LineChartRetries;
