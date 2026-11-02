import { API_BASE_URL } from "../api";

import { ResponsiveLine } from "@nivo/line";
import { useTheme } from "@mui/material";
import { tokens } from "../theme";
import { useEffect, useState } from "react";

const BAND_VALUES = {
    "2G": 2.4,
    "5G": 5,
    "6G": 6,
};

const BAND_LABELS = {
    2.4: "2.4 GHz",
    5: "5 GHz",
    6: "6 GHz",
};

const LineChart = ({
    isCustomLineColors = false,
    isDashboard = false,
}) => {
    const theme = useTheme();
    const colors = tokens(theme.palette.mode);

    const [steeringData, setSteeringData] = useState([]);
    const [error, setError] = useState(null);

    const fetchData = async () => {
        try {
            /*
             * Backend Flask :
             *
             * React/Vite : 3000
             * Flask      : 3001
             */
            const response = await fetch(
                `${API_BASE_URL}/api/station-metrics`
            );

            if (!response.ok) {
                throw new Error(
                    `HTTP error: ${response.status}`
                );
            }

            const metrics = await response.json();

            if (!Array.isArray(metrics)) {
                throw new Error(
                    "Format de données invalide"
                );
            }

		/*
		 * =====================================================
		 * FILTRE : 10 DERNIÈRES MINUTES
		 * =====================================================
		 */

		// Temps actuel en millisecondes
		const now = Date.now();

		// Limite : il y a 10 minutes
		const tenMinutesAgo = now - 10 * 60 * 1000;

		const recentMetrics = metrics.filter((metric) => {
		    if (!metric.timestamp) {
			return false;
		    }

		    let timestamp;

		    // Prend en charge les timestamps Unix en secondes
		    // ou en millisecondes, ainsi que les dates ISO.
		    if (typeof metric.timestamp === "number") {
			timestamp =
			    metric.timestamp < 1e12
				? metric.timestamp * 1000
				: metric.timestamp;
		    } else {
			timestamp = new Date(metric.timestamp).getTime();
		    }

		    if (!Number.isFinite(timestamp)) {
			return false;
		    }

		    // Garde uniquement les mesures des 10 dernières minutes.
		    return timestamp >= tenMinutesAgo && timestamp <= now;
		});

		console.log("=== FILTRE 10 MINUTES ===");
		console.log("Nombre total de mesures :", metrics.length);
		console.log("Mesures récentes :", recentMetrics.length);
		console.log(
		    "Période :",
		    new Date(tenMinutesAgo).toLocaleTimeString(),
		    "→",
		    new Date(now).toLocaleTimeString()
		);
            /*
             * Regroupement des points par station.
             */
            const stations = {};

            recentMetrics.forEach((metric) => {
                const station =
                    metric.station_mac;

                if (!station) {
                    return;
                }

                const bandValue =
                    BAND_VALUES[metric.band];

                /*
                 * Ignore les bandes inconnues.
                 */
                if (bandValue === undefined) {
                    return;
                }

                /*
                 * Vérification du timestamp.
                 */
                const timestamp = new Date(
                    metric.timestamp
                );

                if (
                    Number.isNaN(
                        timestamp.getTime()
                    )
                ) {
                    return;
                }

                if (!stations[station]) {
                    stations[station] = [];
                }

                stations[station].push({
                    x: timestamp,
                    y: bandValue,

                    /*
                     * Informations supplémentaires
                     * pour le tooltip.
                     */
                    band: metric.band,
                    rssi: metric.rssi,
                    clients: metric.clients,
                    airtime: metric.airtime,
                });
            });

            /*
             * =====================================================
             * TRANSFORMATION NIVO
             * =====================================================
             *
             * Une ligne = une station.
             */
            const data = Object.entries(
                stations
            ).map(([station, points]) => ({
                id: station,

                data: points.sort(
                    (a, b) =>
                        a.x.getTime() -
                        b.x.getTime()
                ),
            }));

            console.log(
                "=== STATIONS ==="
            );

            data.forEach((station) => {
                console.log(
                    station.id,
                    "points:",
                    station.data.length,
                    "data:",
                    station.data
                );
            });

            console.log(
                "Nombre total de stations:",
                data.length
            );

            setSteeringData(data);
            setError(null);
        } catch (err) {
            console.error(
                "Erreur récupération station metrics:",
                err
            );

            setError(
                "Impossible de récupérer les données du backend."
            );
        }
    };

    useEffect(() => {
        /*
         * Premier chargement.
         */
        fetchData();

        /*
         * Actualisation toutes les 5 secondes.
         */
        const interval = setInterval(
            fetchData,
            5000
        );

        return () => {
            clearInterval(interval);
        };
    }, []);

    return (
        <div
            style={{
                width: "100%",
                height: "100%",
                minHeight: "400px",
                position: "relative",
            }}
        >
            {error && (
                <div
                    style={{
                        position: "absolute",
                        top: 10,
                        left: 10,
                        zIndex: 10,
                        padding: "8px 12px",
                        borderRadius: "4px",
                        background: "#c62828",
                        color: "#fff",
                    }}
                >
                    {error}
                </div>
            )}

            {steeringData.length === 0 &&
                !error && (
                    <div
                        style={{
                            position: "absolute",
                            top: "50%",
                            left: "50%",
                            transform:
                                "translate(-50%, -50%)",
                            color:
                                colors.grey[300],
                        }}
                    >
                        Aucune donnée disponible
                    </div>
                )}

            <ResponsiveLine
                data={steeringData}

                /*
                 * =====================================================
                 * THEME
                 * =====================================================
                 */
                theme={{
                    axis: {
                        domain: {
                            line: {
                                stroke:
                                    colors.grey[100],
                            },
                        },

                        legend: {
                            text: {
                                fill:
                                    colors.grey[100],
                            },
                        },

                        ticks: {
                            line: {
                                stroke:
                                    colors.grey[100],
                                strokeWidth: 1,
                            },

                            text: {
                                fill:
                                    colors.grey[100],
                            },
                        },
                    },

                    legends: {
                        text: {
                            fill:
                                colors.grey[100],
                        },
                    },

                    tooltip: {
                        container: {
                            color:
                                colors.grey[900],
                        },
                    },
                }}

                /*
                 * =====================================================
                 * COULEURS
                 * =====================================================
                 */
                colors={
                    isCustomLineColors
                        ? [
                              colors.greenAccent[
                                  500
                              ],
                              colors.blueAccent[
                                  500
                              ],
                              colors.redAccent[
                                  500
                              ],
                          ]
                        : {
                              scheme:
                                  "category10",
                          }
                }

                /*
                 * =====================================================
                 * MARGES
                 * =====================================================
                 */
                margin={{
                    top: 50,
                    right: 180,
                    bottom: 70,
                    left: 90,
                }}

                /*
                 * =====================================================
                 * AXE X = TEMPS
                 * =====================================================
                 */
                xScale={{
                    type: "time",
                    format: "native",
                    precision: "second",
                    useUTC: false,
                }}

                /*
                 * =====================================================
                 * AXE Y = BANDE WIFI
                 * =====================================================
                 */
                yScale={{
                    type: "linear",
                    min: 2,
                    max: 6.2,
                    stacked: false,
                    reverse: false,
                }}

                /*
                 * =====================================================
                 * AXE X
                 * =====================================================
                 *
                 * On affiche les minutes.
                 *
                 * tickValues={10} évite d'avoir trop de labels
                 * et garde le graphique léger.
                 */
                axisBottom={{
                    format: "%H:%M",

                    tickValues: 10,

                    tickSize: 5,

                    tickPadding: 8,

                    tickRotation: -45,

                    legend:
                        isDashboard
                            ? undefined
                            : "Time",

                    legendOffset: 55,

                    legendPosition: "middle",
                }}

                /*
                 * =====================================================
                 * AXE Y
                 * =====================================================
                 */
                axisLeft={{
                    tickValues: [
                        2.4,
                        5,
                        6,
                    ],

                    tickSize: 5,

                    tickPadding: 8,

                    tickRotation: 0,

                    legend:
                        isDashboard
                            ? undefined
                            : "Wi-Fi Band",

                    legendOffset: -70,

                    legendPosition: "middle",

                    format: (value) =>
                        BAND_LABELS[value] ??
                        value,
                }}

                axisTop={null}

                axisRight={null}

                /*
                 * Pas de grille verticale.
                 */
                enableGridX={false}

                /*
                 * Grille horizontale.
                 */
                enableGridY={true}

                /*
                 * =====================================================
                 * COURBE
                 * =====================================================
                 */
                curve="stepAfter"

                lineWidth={3}

                pointSize={7}

                pointColor={{
                    theme: "background",
                }}

                pointBorderWidth={2}

                pointBorderColor={{
                    from: "serieColor",
                }}

                enableArea={false}

                useMesh={true}

                /*
                 * =====================================================
                 * TOOLTIP
                 * =====================================================
                 */
                tooltip={({ point }) => {
                    const data = point.data;

                    const timestamp =
                        data.x instanceof Date
                            ? data.x
                            : new Date(data.x);

                    return (
                        <div
                            style={{
                                background:
                                    colors.primary[500],

                                padding:
                                    "10px 14px",

                                borderRadius:
                                    "6px",

                                boxShadow:
                                    "0 2px 8px rgba(0,0,0,0.25)",

                                color: "#fff",

                                minWidth: "180px",
                            }}
                        >
                            <strong>
                                Station
                            </strong>

                            <br />

                            {point.serieId}

                            <br />
                            <br />

                            <strong>
                                Time
                            </strong>

                            <br />

                            {timestamp.toLocaleString()}

                            <br />
                            <br />

                            <strong>
                                Band
                            </strong>

                            <br />

                            {BAND_LABELS[data.y] ??
                                data.band}

                            <br />
                            <br />

                            <strong>
                                RSSI
                            </strong>

                            <br />

                            {data.rssi ??
                                "N/A"}{" "}
                            dBm

                            <br />
                            <br />

                            <strong>
                                Clients
                            </strong>

                            <br />

                            {data.clients ??
                                "N/A"}

                            <br />
                            <br />

                            <strong>
                                Airtime
                            </strong>

                            <br />

                            {data.airtime ??
                                "N/A"}
                        </div>
                    );
                }}

                /*
                 * =====================================================
                 * LEGEND
                 * =====================================================
                 */
                legends={[
                    {
                        anchor:
                            "bottom-right",

                        direction:
                            "column",

                        justify: false,

                        translateX: 170,

                        translateY: 0,

                        itemsSpacing: 8,

                        itemDirection:
                            "left-to-right",

                        itemWidth: 150,

                        itemHeight: 20,

                        itemOpacity: 0.85,

                        symbolSize: 12,

                        symbolShape: "circle",

                        effects: [
                            {
                                on: "hover",

                                style: {
                                    itemBackground:
                                        "rgba(0, 0, 0, .03)",

                                    itemOpacity: 1,
                                },
                            },
                        ],
                    },
                ]}
            />
        </div>
    );
};

export default LineChart;


