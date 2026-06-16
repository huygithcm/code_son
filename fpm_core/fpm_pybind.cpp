// fpm_pybind.cpp — module Python "fpm" bọc CFastMatch bằng pybind11.
// Nhận numpy.ndarray (uint8, gray HxW hoặc màu HxWx3), trả list dict kết quả.
#include "fpm_core.h"

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>

namespace py = pybind11;
using namespace fpm;

// numpy uint8 -> cv::Mat (clone để sở hữu dữ liệu, an toàn ngoài GIL về sau).
static cv::Mat NumpyToMat (py::array_t<uint8_t, py::array::c_style | py::array::forcecast> arr)
{
	py::buffer_info buf = arr.request ();
	if (buf.ndim != 2 && buf.ndim != 3)
		throw std::invalid_argument ("image phải là mảng 2D (gray) hoặc 3D (HxWxC) uint8");
	int h = (int)buf.shape[0];
	int w = (int)buf.shape[1];
	int ch = (buf.ndim == 3) ? (int)buf.shape[2] : 1;
	cv::Mat m (h, w, CV_8UC (ch), buf.ptr);
	return m.clone ();
}

// vector<s_SingleTargetMatch> -> list[dict]
static py::list ResultsToPy (const std::vector<s_SingleTargetMatch>& res)
{
	py::list out;
	for (const auto& s : res)
	{
		py::dict d;
		d["score"] = s.dMatchScore;
		d["angle"] = s.dMatchedAngle;
		d["center"] = py::make_tuple (s.ptCenter.x, s.ptCenter.y);
		d["corners"] = py::make_tuple (
			py::make_tuple (s.ptLT.x, s.ptLT.y),
			py::make_tuple (s.ptRT.x, s.ptRT.y),
			py::make_tuple (s.ptRB.x, s.ptRB.y),
			py::make_tuple (s.ptLB.x, s.ptLB.y));
		out.append (d);
	}
	return out;
}

PYBIND11_MODULE (fpm, m)
{
	m.doc () = "Fastest Image Pattern Matching — core C++ (NCC + pyramid + rotation), tách khỏi MFC.";

	py::class_<MatchParams> (m, "MatchParams")
		.def (py::init<> ())
		.def_readwrite ("max_pos", &MatchParams::iMaxPos)
		.def_readwrite ("max_overlap", &MatchParams::dMaxOverlap)
		.def_readwrite ("score", &MatchParams::dScore)
		.def_readwrite ("tolerance_angle", &MatchParams::dToleranceAngle)
		.def_readwrite ("min_reduce_area", &MatchParams::iMinReduceArea)
		.def_readwrite ("tolerance_range", &MatchParams::bToleranceRange)
		.def_readwrite ("tolerance1", &MatchParams::dTolerance1)
		.def_readwrite ("tolerance2", &MatchParams::dTolerance2)
		.def_readwrite ("tolerance3", &MatchParams::dTolerance3)
		.def_readwrite ("tolerance4", &MatchParams::dTolerance4)
		.def_readwrite ("stop_layer1", &MatchParams::bStopLayer1)
		.def_readwrite ("bitwise_not", &MatchParams::bBitwiseNot)
		.def_readwrite ("use_simd", &MatchParams::bUseSIMD)
		.def_readwrite ("sub_pixel", &MatchParams::bSubPixel)
		.def ("__repr__", [] (const MatchParams& p) {
			return "<MatchParams score=" + std::to_string (p.dScore) +
				" max_pos=" + std::to_string (p.iMaxPos) +
				" tol_angle=" + std::to_string (p.dToleranceAngle) + ">";
		});

	py::class_<CFastMatch> (m, "FastMatch")
		.def (py::init<> ())
		.def ("learn",
			[] (CFastMatch& self, py::array tmpl, const MatchParams& p) {
				self.LearnPattern (NumpyToMat (tmpl), p);
			},
			py::arg ("template_img"), py::arg ("params") = MatchParams (),
			"Học template từ ảnh numpy uint8.")
		.def ("match",
			[] (CFastMatch& self, py::array src, const MatchParams& p) {
				auto res = self.Match (NumpyToMat (src), p);
				return ResultsToPy (res);
			},
			py::arg ("source_img"), py::arg ("params") = MatchParams (),
			"Tìm template trong ảnh nguồn. Trả list[dict]: score, angle, center, corners.")
		.def ("is_learned", &CFastMatch::IsPatternLearned)
		.def ("__repr__", [] (const CFastMatch& self) {
			return std::string ("<FastMatch learned=") + (self.IsPatternLearned () ? "True" : "False") + ">";
		});

	// Tiện ích 1 phát: learn + match.
	m.def ("match",
		[] (py::array src, py::array tmpl, const MatchParams& p) {
			CFastMatch matcher;
			matcher.LearnPattern (NumpyToMat (tmpl), p);
			auto res = matcher.Match (NumpyToMat (src), p);
			return ResultsToPy (res);
		},
		py::arg ("source_img"), py::arg ("template_img"), py::arg ("params") = MatchParams (),
		"Hàm tiện ích: học template rồi match trong 1 lời gọi.");
}
