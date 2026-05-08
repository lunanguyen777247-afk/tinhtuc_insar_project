import React, { useState } from 'react';
import { 
  AlertTriangle, 
  Activity, 
  BarChart2, 
  FileText, 
  Download, 
  MapPin,
  CheckCircle2,
  X,
  Info,
  Database,
  Radio,
  Layers
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

export function Dashboard() {
  const [showAlert, setShowAlert] = useState(true);

  // SVG Chart Data Generator
  // Mocking 2020 to 2026
  const years = [2020, 2021, 2022, 2023, 2024, 2025, 2026];
  const chartHeight = 300;
  const chartWidth = 600;
  const padding = 40;
  const innerWidth = chartWidth - padding * 2;
  const innerHeight = chartHeight - padding * 2;

  // Mock displacement data (mm)
  const p1Data = [0, -2, -5, -12, -18, -25, -30];
  const p2Data = [0, -8, -20, -35, -55, -72, -84.9];
  const p3Data = [0, -1, -2, -3, -5, -7, -9];

  // Scale functions
  const xStep = innerWidth / (years.length - 1);
  const yScale = (val: number) => {
    const min = -90;
    const max = 10;
    const range = max - min;
    return padding + innerHeight - ((val - min) / range) * innerHeight;
  };

  const getPath = (data: number[]) => {
    return data.map((val, i) => `${i === 0 ? 'M' : 'L'} ${padding + i * xStep} ${yScale(val)}`).join(' ');
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans p-6 pb-20">
      <div className="max-w-6xl mx-auto space-y-8">
        
        {/* Header / Hero */}
        <header className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 border-b border-slate-800 pb-6">
          <div>
            <h1 className="text-3xl md:text-4xl font-bold tracking-tight text-slate-50 flex items-center gap-3">
              <Activity className="h-8 w-8 text-cyan-500" />
              Cổng Giám Sát Địa Chất Tĩnh Túc
            </h1>
            <p className="text-slate-400 mt-2 text-lg">Hệ thống theo dõi chuyển vị mặt đất bằng vệ tinh InSAR</p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <Badge variant="outline" className="bg-cyan-500/10 text-cyan-400 border-cyan-500/20 px-3 py-1">
              <Radio className="h-3 w-3 mr-2 animate-pulse" />
              Đang hoạt động
            </Badge>
            <span className="text-sm text-slate-500">Cập nhật lần cuối: 08-05-2026</span>
          </div>
        </header>

        {/* Alert Banner */}
        {showAlert && (
          <Alert className="bg-orange-500/10 border-orange-500/50 text-orange-200 flex items-start gap-4 [&>svg]:text-orange-400">
            <AlertTriangle className="h-5 w-5 mt-0.5" />
            <div className="flex-1">
              <AlertTitle className="text-lg font-semibold text-orange-400">Cảnh báo hệ thống</AlertTitle>
              <AlertDescription className="text-orange-200/80">
                53 sự kiện cảnh báo phát hiện — Theo dõi liên tục đang hoạt động.
              </AlertDescription>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="bg-slate-950/50 border-orange-500/30 hover:bg-orange-500/20 hover:text-orange-100">
                Xem chi tiết
              </Button>
              <Button variant="ghost" size="icon" className="hover:bg-orange-500/20 hover:text-orange-100" onClick={() => setShowAlert(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          </Alert>
        )}

        {/* Stats Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card className="bg-slate-900 border-slate-800">
            <CardContent className="p-6">
              <div className="flex items-center justify-between space-y-0 pb-2">
                <p className="text-sm font-medium text-slate-400">Điểm giám sát</p>
                <MapPin className="h-4 w-4 text-cyan-500" />
              </div>
              <div className="text-3xl font-bold text-slate-100">3</div>
              <p className="text-xs text-slate-500 mt-1">Hotspot nguy cơ cao</p>
            </CardContent>
          </Card>
          <Card className="bg-slate-900 border-slate-800">
            <CardContent className="p-6">
              <div className="flex items-center justify-between space-y-0 pb-2">
                <p className="text-sm font-medium text-slate-400">Sự kiện cảnh báo</p>
                <AlertTriangle className="h-4 w-4 text-orange-500" />
              </div>
              <div className="text-3xl font-bold text-orange-400">53</div>
              <p className="text-xs text-slate-500 mt-1">Cần đánh giá thực địa</p>
            </CardContent>
          </Card>
          <Card className="bg-slate-900 border-slate-800">
            <CardContent className="p-6">
              <div className="flex items-center justify-between space-y-0 pb-2">
                <p className="text-sm font-medium text-slate-400">Tốc độ lún tối đa</p>
                <BarChart2 className="h-4 w-4 text-rose-500" />
              </div>
              <div className="text-3xl font-bold text-slate-100">11.1</div>
              <p className="text-xs text-slate-500 mt-1">mm/năm</p>
            </CardContent>
          </Card>
          <Card className="bg-slate-900 border-slate-800">
            <CardContent className="p-6">
              <div className="flex items-center justify-between space-y-0 pb-2">
                <p className="text-sm font-medium text-slate-400">Dữ liệu hàng ngày</p>
                <Database className="h-4 w-4 text-cyan-500" />
              </div>
              <div className="text-3xl font-bold text-slate-100">1,645</div>
              <p className="text-xs text-slate-500 mt-1">bản ghi từ 06/2020</p>
            </CardContent>
          </Card>
        </div>

        {/* Map & Chart Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Interactive Map Panel */}
          <Card className="bg-slate-900 border-slate-800 overflow-hidden flex flex-col">
            <CardHeader className="border-b border-slate-800 pb-4">
              <CardTitle className="text-lg flex items-center gap-2">
                <MapPin className="h-5 w-5 text-cyan-500" /> Bản Đồ Khu Vực Tĩnh Túc
              </CardTitle>
              <CardDescription className="text-slate-400">Khu vực khai thác và điểm giám sát (AOI: ~22.7°N, 106.1°E)</CardDescription>
            </CardHeader>
            <CardContent className="p-0 flex-1 relative bg-[#0a0f1a] min-h-[350px]">
              <svg viewBox="0 0 400 300" className="w-full h-full text-slate-700" preserveAspectRatio="xMidYMid slice">
                {/* Terrain contour lines */}
                <path d="M0 50 Q 100 20, 200 60 T 400 30" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.3"/>
                <path d="M0 100 Q 150 80, 250 120 T 400 90" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.4"/>
                <path d="M0 150 Q 120 180, 220 150 T 400 170" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.3"/>
                <path d="M0 200 Q 180 250, 300 200 T 400 250" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.4"/>
                
                {/* Mine boundary */}
                <path d="M 120 80 L 280 60 L 320 140 L 180 180 Z" fill="none" stroke="#06b6d4" strokeWidth="2" strokeDasharray="4 4" opacity="0.6"/>
                <text x="160" y="120" fill="#06b6d4" fontSize="12" opacity="0.6">Mỏ thiếc Tĩnh Túc</text>

                {/* Hotspot Markers */}
                {/* P1 */}
                <circle cx="280" cy="100" r="6" fill="#facc15" className="animate-pulse"/>
                <text x="290" y="104" fill="#facc15" fontSize="12" fontWeight="bold">P1</text>

                {/* P2 */}
                <circle cx="220" cy="160" r="8" fill="#f97316" className="animate-pulse"/>
                <circle cx="220" cy="160" r="16" fill="#f97316" opacity="0.2" className="animate-ping"/>
                <text x="235" y="164" fill="#f97316" fontSize="12" fontWeight="bold">P2</text>

                {/* P3 */}
                <circle cx="150" cy="200" r="6" fill="#22c55e"/>
                <text x="160" y="204" fill="#22c55e" fontSize="12" fontWeight="bold">P3</text>
              </svg>

              {/* Legend */}
              <div className="absolute bottom-4 right-4 bg-slate-950/80 backdrop-blur-sm border border-slate-800 p-3 rounded-lg text-xs space-y-2">
                <div className="font-semibold text-slate-300 mb-1">Mức độ nguy cơ</div>
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-green-500"></div> <span className="text-slate-400">Thấp</span></div>
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-yellow-400"></div> <span className="text-slate-400">Trung bình</span></div>
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-orange-500"></div> <span className="text-slate-400">Cao</span></div>
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-red-500"></div> <span className="text-slate-400">Nguy hiểm</span></div>
              </div>
            </CardContent>
          </Card>

          {/* Deformation Time-Series Chart */}
          <Card className="bg-slate-900 border-slate-800 overflow-hidden flex flex-col">
            <CardHeader className="border-b border-slate-800 pb-4">
              <CardTitle className="text-lg flex items-center gap-2">
                <BarChart2 className="h-5 w-5 text-cyan-500" /> Chuỗi Thời Gian Chuyển Vị
              </CardTitle>
              <CardDescription className="text-slate-400">Theo dõi chuyển vị tích lũy (2020-2026)</CardDescription>
            </CardHeader>
            <CardContent className="p-6 flex-1 flex flex-col items-center justify-center min-h-[350px]">
              <div className="w-full relative">
                <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="w-full h-auto drop-shadow-md">
                  {/* Grid Lines */}
                  {[0, -20, -40, -60, -80].map((val) => (
                    <g key={val}>
                      <line x1={padding} y1={yScale(val)} x2={chartWidth - padding} y2={yScale(val)} stroke="#334155" strokeWidth="1" strokeDasharray="4 4" />
                      <text x={padding - 10} y={yScale(val) + 4} fill="#64748b" fontSize="12" textAnchor="end">{val}</text>
                    </g>
                  ))}
                  
                  {/* Axes */}
                  <line x1={padding} y1={yScale(0)} x2={chartWidth - padding} y2={yScale(0)} stroke="#64748b" strokeWidth="2" />
                  <line x1={padding} y1={padding} x2={padding} y2={chartHeight - padding} stroke="#64748b" strokeWidth="2" />
                  
                  {/* X Axis Labels */}
                  {years.map((year, i) => (
                    <text key={year} x={padding + i * xStep} y={chartHeight - padding + 20} fill="#64748b" fontSize="12" textAnchor="middle">{year}</text>
                  ))}

                  {/* Axis Titles */}
                  <text x={chartWidth / 2} y={chartHeight - 5} fill="#94a3b8" fontSize="12" textAnchor="middle">Thời gian</text>
                  <text x={10} y={chartHeight / 2} fill="#94a3b8" fontSize="12" textAnchor="middle" transform={`rotate(-90 15 ${chartHeight/2})`}>Chuyển vị (mm)</text>

                  {/* Data Lines */}
                  {/* P3 - Green */}
                  <path d={getPath(p3Data)} fill="none" stroke="#22c55e" strokeWidth="3" />
                  {/* P1 - Yellow */}
                  <path d={getPath(p1Data)} fill="none" stroke="#facc15" strokeWidth="3" />
                  {/* P2 - Orange */}
                  <path d={getPath(p2Data)} fill="none" stroke="#f97316" strokeWidth="3" />

                  {/* Data Points */}
                  {years.map((_, i) => (
                    <g key={i}>
                      <circle cx={padding + i * xStep} cy={yScale(p3Data[i])} r="4" fill="#22c55e" />
                      <circle cx={padding + i * xStep} cy={yScale(p1Data[i])} r="4" fill="#facc15" />
                      <circle cx={padding + i * xStep} cy={yScale(p2Data[i])} r="4" fill="#f97316" />
                    </g>
                  ))}
                </svg>

                {/* Legend Overlay */}
                <div className="absolute top-0 right-4 bg-slate-950/80 backdrop-blur-sm border border-slate-800 p-2 rounded-lg text-xs flex gap-4">
                  <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-yellow-400"></div> <span className="text-slate-300">P1</span></div>
                  <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-orange-500"></div> <span className="text-slate-300">P2</span></div>
                  <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-green-500"></div> <span className="text-slate-300">P3</span></div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Hotspot Risk Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="bg-slate-900 border-slate-800">
            <CardContent className="p-6 space-y-4">
              <div className="flex justify-between items-start">
                <h3 className="font-semibold text-lg text-slate-100 leading-tight">P1: Sườn dốc khu khai thác thiếc phía Đông</h3>
                <Badge className="bg-yellow-400/20 text-yellow-400 border border-yellow-400/30 hover:bg-yellow-400/20">Trung bình</Badge>
              </div>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Chuyển vị tối đa:</span>
                  <span className="text-slate-200 font-mono">-30.0 mm</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Yếu tố ảnh hưởng:</span>
                  <span className="text-slate-200">Độ ẩm đất / Mưa</span>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-2 border-t border-slate-800 text-sm text-yellow-400">
                <Activity className="h-4 w-4" />
                <span>Đang theo dõi</span>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-slate-900 border-slate-800 border-t-2 border-t-orange-500 relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-b from-orange-500/5 to-transparent pointer-events-none" />
            <CardContent className="p-6 space-y-4">
              <div className="flex justify-between items-start">
                <h3 className="font-semibold text-lg text-slate-100 leading-tight">P2: Talus slope có dấu hiệu trượt</h3>
                <Badge className="bg-orange-500/20 text-orange-400 border border-orange-500/30 hover:bg-orange-500/20">Cao</Badge>
              </div>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Chuyển vị tối đa:</span>
                  <span className="text-rose-400 font-mono font-bold">-84.9 mm</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Yếu tố ảnh hưởng:</span>
                  <span className="text-slate-200">Độ ẩm đất / Mưa</span>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-2 border-t border-slate-800 text-sm text-orange-400">
                <AlertTriangle className="h-4 w-4" />
                <span className="font-semibold">Cảnh báo biến dạng hỗn hợp</span>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-slate-900 border-slate-800">
            <CardContent className="p-6 space-y-4">
              <div className="flex justify-between items-start">
                <h3 className="font-semibold text-lg text-slate-100 leading-tight">P3: Khu dân cư cạnh mỏ kẽm</h3>
                <Badge className="bg-green-500/20 text-green-400 border border-green-500/30 hover:bg-green-500/20">Thấp</Badge>
              </div>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Chuyển vị tối đa:</span>
                  <span className="text-slate-200 font-mono">-9.0 mm</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Yếu tố ảnh hưởng:</span>
                  <span className="text-slate-200">Tự nhiên</span>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-2 border-t border-slate-800 text-sm text-green-400">
                <CheckCircle2 className="h-4 w-4" />
                <span>Ổn định</span>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Download Reports Section */}
        <div>
          <h2 className="text-xl font-semibold mb-4 text-slate-100 flex items-center gap-2">
            <Layers className="h-5 w-5 text-cyan-500" /> Dữ liệu & Báo cáo
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card className="bg-slate-900 border-slate-800 hover:border-cyan-500/30 transition-colors group cursor-pointer">
              <CardContent className="p-5 flex items-center gap-4">
                <div className="p-3 bg-cyan-500/10 rounded-lg group-hover:bg-cyan-500/20 transition-colors">
                  <MapPin className="h-6 w-6 text-cyan-400" />
                </div>
                <div className="flex-1">
                  <h4 className="font-medium text-slate-200">Báo cáo vận tốc</h4>
                  <p className="text-xs text-slate-500">Bản đồ vận tốc trung bình (Velocity map)</p>
                </div>
                <Button variant="ghost" size="icon" className="text-slate-400 hover:text-cyan-400 hover:bg-cyan-500/10 rounded-full">
                  <Download className="h-5 w-5" />
                </Button>
              </CardContent>
            </Card>

            <Card className="bg-slate-900 border-slate-800 hover:border-cyan-500/30 transition-colors group cursor-pointer">
              <CardContent className="p-5 flex items-center gap-4">
                <div className="p-3 bg-indigo-500/10 rounded-lg group-hover:bg-indigo-500/20 transition-colors">
                  <Activity className="h-6 w-6 text-indigo-400" />
                </div>
                <div className="flex-1">
                  <h4 className="font-medium text-slate-200">Chuỗi thời gian 4D</h4>
                  <p className="text-xs text-slate-500">Phân tích chuỗi thời gian chuyển vị</p>
                </div>
                <Button variant="ghost" size="icon" className="text-slate-400 hover:text-indigo-400 hover:bg-indigo-500/10 rounded-full">
                  <Download className="h-5 w-5" />
                </Button>
              </CardContent>
            </Card>

            <Card className="bg-slate-900 border-slate-800 hover:border-cyan-500/30 transition-colors group cursor-pointer">
              <CardContent className="p-5 flex items-center gap-4">
                <div className="p-3 bg-purple-500/10 rounded-lg group-hover:bg-purple-500/20 transition-colors">
                  <Info className="h-6 w-6 text-purple-400" />
                </div>
                <div className="flex-1">
                  <h4 className="font-medium text-slate-200">Biến dạng tensor</h4>
                  <p className="text-xs text-slate-500">Phân tích ứng suất & biến dạng (Strain analysis)</p>
                </div>
                <Button variant="ghost" size="icon" className="text-slate-400 hover:text-purple-400 hover:bg-purple-500/10 rounded-full">
                  <Download className="h-5 w-5" />
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>

      </div>

      {/* Footer */}
      <footer className="max-w-6xl mx-auto mt-12 pt-6 border-t border-slate-800 text-center text-sm text-slate-500 pb-4">
        <p>Dữ liệu từ Sentinel-1 / ALOS-2 · Xử lý bởi InSAR Pipeline · © 2026 Dự án Giám sát Tĩnh Túc</p>
      </footer>
    </div>
  );
}
