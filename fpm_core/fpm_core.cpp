// fpm_core.cpp — port các hàm lõi thuần OpenCV từ MatchToolDlg.cpp (bỏ MFC).
#include "fpm_core.h"

#include <intrin.h>   // SSE intrinsics (__m128i, _mm_*) — MSVC
#include <algorithm>
#include <cmath>
#include <cfloat>

namespace fpm {

using std::max;
using std::min;
using std::sort;
using std::vector;

// ===================== Comparator =====================
bool compareScoreBig2Small (const s_MatchParameter& lhs, const s_MatchParameter& rhs)
{
	return lhs.dMatchScore > rhs.dMatchScore;
}
bool comparePtWithAngle (const std::pair<Point2f, double> lhs, const std::pair<Point2f, double> rhs)
{
	return lhs.second < rhs.second;
}

// ===================== s_BlockMax =====================
s_BlockMax::s_BlockMax (Mat matSrc_, Size sizeTemplate)
{
	matSrc = matSrc_;
	// 將matSrc 拆成數個block，分別計算最大值
	int iBlockW = sizeTemplate.width * 2;
	int iBlockH = sizeTemplate.height * 2;

	int iCol = matSrc.cols / iBlockW;
	bool bHResidue = matSrc.cols % iBlockW != 0;

	int iRow = matSrc.rows / iBlockH;
	bool bVResidue = matSrc.rows % iBlockH != 0;

	if (iCol == 0 || iRow == 0)
	{
		vecBlock.clear ();
		return;
	}

	vecBlock.resize (iCol * iRow);
	int iCount = 0;
	for (int y = 0; y < iRow; y++)
	{
		for (int x = 0; x < iCol; x++)
		{
			Rect rectBlock (x * iBlockW, y * iBlockH, iBlockW, iBlockH);
			vecBlock[iCount].rect = rectBlock;
			cv::minMaxLoc (matSrc (rectBlock), 0, &vecBlock[iCount].dMax, 0, &vecBlock[iCount].ptMaxLoc);
			vecBlock[iCount].ptMaxLoc += rectBlock.tl ();
			iCount++;
		}
	}
	if (bHResidue && bVResidue)
	{
		Rect rectRight (iCol * iBlockW, 0, matSrc.cols - iCol * iBlockW, matSrc.rows);
		Block blockRight;
		blockRight.rect = rectRight;
		cv::minMaxLoc (matSrc (rectRight), 0, &blockRight.dMax, 0, &blockRight.ptMaxLoc);
		blockRight.ptMaxLoc += rectRight.tl ();
		vecBlock.push_back (blockRight);

		Rect rectBottom (0, iRow * iBlockH, iCol * iBlockW, matSrc.rows - iRow * iBlockH);
		Block blockBottom;
		blockBottom.rect = rectBottom;
		cv::minMaxLoc (matSrc (rectBottom), 0, &blockBottom.dMax, 0, &blockBottom.ptMaxLoc);
		blockBottom.ptMaxLoc += rectBottom.tl ();
		vecBlock.push_back (blockBottom);
	}
	else if (bHResidue)
	{
		Rect rectRight (iCol * iBlockW, 0, matSrc.cols - iCol * iBlockW, matSrc.rows);
		Block blockRight;
		blockRight.rect = rectRight;
		cv::minMaxLoc (matSrc (rectRight), 0, &blockRight.dMax, 0, &blockRight.ptMaxLoc);
		blockRight.ptMaxLoc += rectRight.tl ();
		vecBlock.push_back (blockRight);
	}
	else
	{
		Rect rectBottom (0, iRow * iBlockH, matSrc.cols, matSrc.rows - iRow * iBlockH);
		Block blockBottom;
		blockBottom.rect = rectBottom;
		cv::minMaxLoc (matSrc (rectBottom), 0, &blockBottom.dMax, 0, &blockBottom.ptMaxLoc);
		blockBottom.ptMaxLoc += rectBottom.tl ();
		vecBlock.push_back (blockBottom);
	}
}
void s_BlockMax::UpdateMax (Rect rectIgnore)
{
	if (vecBlock.size () == 0)
		return;
	int iSize = (int)vecBlock.size ();
	for (int i = 0; i < iSize; i++)
	{
		Rect rectIntersec = rectIgnore & vecBlock[i].rect;
		if (rectIntersec.width == 0 && rectIntersec.height == 0)
			continue;
		cv::minMaxLoc (matSrc (vecBlock[i].rect), 0, &vecBlock[i].dMax, 0, &vecBlock[i].ptMaxLoc);
		vecBlock[i].ptMaxLoc += vecBlock[i].rect.tl ();
	}
}
void s_BlockMax::GetMaxValueLoc (double& dMax, Point& ptMaxLoc)
{
	int iSize = (int)vecBlock.size ();
	if (iSize == 0)
	{
		cv::minMaxLoc (matSrc, 0, &dMax, 0, &ptMaxLoc);
		return;
	}
	int iIndex = 0;
	dMax = vecBlock[0].dMax;
	for (int i = 1; i < iSize; i++)
	{
		if (vecBlock[i].dMax >= dMax)
		{
			iIndex = i;
			dMax = vecBlock[i].dMax;
		}
	}
	ptMaxLoc = vecBlock[iIndex].ptMaxLoc;
}

// ===================== SIMD helpers (From ImageShop) =====================
// 4個有符號的32位的數據相加的和。
static inline int _mm_hsum_epi32 (__m128i V)   // V3 V2 V1 V0
{
	__m128i T = _mm_add_epi32 (V, _mm_srli_si128 (V, 8));
	T = _mm_add_epi32 (T, _mm_srli_si128 (T, 4));
	return _mm_cvtsi128_si32 (T);
}
// 基於SSE的字節數據的乘法。
static inline int IM_Conv_SIMD (unsigned char* pCharKernel, unsigned char* pCharConv, int iLength)
{
	const int iBlockSize = 16, Block = iLength / iBlockSize;
	__m128i SumV = _mm_setzero_si128 ();
	__m128i Zero = _mm_setzero_si128 ();
	for (int Y = 0; Y < Block * iBlockSize; Y += iBlockSize)
	{
		__m128i SrcK = _mm_loadu_si128 ((__m128i*)(pCharKernel + Y));
		__m128i SrcC = _mm_loadu_si128 ((__m128i*)(pCharConv + Y));
		__m128i SrcK_L = _mm_unpacklo_epi8 (SrcK, Zero);
		__m128i SrcK_H = _mm_unpackhi_epi8 (SrcK, Zero);
		__m128i SrcC_L = _mm_unpacklo_epi8 (SrcC, Zero);
		__m128i SrcC_H = _mm_unpackhi_epi8 (SrcC, Zero);
		__m128i SumT = _mm_add_epi32 (_mm_madd_epi16 (SrcK_L, SrcC_L), _mm_madd_epi16 (SrcK_H, SrcC_H));
		SumV = _mm_add_epi32 (SumV, SumT);
	}
	int Sum = _mm_hsum_epi32 (SumV);
	for (int Y = Block * iBlockSize; Y < iLength; Y++)
		Sum += pCharKernel[Y] * pCharConv[Y];
	return Sum;
}

// ===================== Hàm lõi =====================
int GetTopLayer (Mat* matTempl, int iMinDstLength)
{
	int iTopLayer = 0;
	int iMinReduceArea = iMinDstLength * iMinDstLength;
	int iArea = matTempl->cols * matTempl->rows;
	while (iArea > iMinReduceArea)
	{
		iArea /= 4;
		iTopLayer++;
	}
	return iTopLayer;
}

void MatchTemplate (Mat& matSrc, s_TemplData* pTemplData, Mat& matResult, int iLayer, bool bUseSIMD)
{
	if (bUseSIMD)
	{
		// From ImageShop
		matResult.create (matSrc.rows - pTemplData->vecPyramid[iLayer].rows + 1,
			matSrc.cols - pTemplData->vecPyramid[iLayer].cols + 1, CV_32FC1);
		matResult.setTo (0);
		Mat& matTemplate = pTemplData->vecPyramid[iLayer];

		int t_r_end = matTemplate.rows, t_r = 0;
		for (int r = 0; r < matResult.rows; r++)
		{
			float* r_matResult = matResult.ptr<float> (r);
			uchar* r_source = matSrc.ptr<uchar> (r);
			uchar* r_template, * r_sub_source;
			for (int c = 0; c < matResult.cols; ++c, ++r_matResult, ++r_source)
			{
				r_template = matTemplate.ptr<uchar> ();
				r_sub_source = r_source;
				for (t_r = 0; t_r < t_r_end; ++t_r, r_sub_source += matSrc.cols, r_template += matTemplate.cols)
					*r_matResult = *r_matResult + IM_Conv_SIMD (r_template, r_sub_source, matTemplate.cols);
			}
		}
		// From ImageShop
	}
	else
		cv::matchTemplate (matSrc, pTemplData->vecPyramid[iLayer], matResult, CV_TM_CCORR);

	CCOEFF_Denominator (matSrc, pTemplData, matResult, iLayer);
}

void GetRotatedROI (Mat& matSrc, Size size, Point2f ptLT, double dAngle, Mat& matROI)
{
	double dAngle_radian = dAngle * D2R;
	Point2f ptC ((matSrc.cols - 1) / 2.0f, (matSrc.rows - 1) / 2.0f);
	Point2f ptLT_rotate = ptRotatePt2f (ptLT, ptC, dAngle_radian);
	Size sizePadding (size.width + 6, size.height + 6);

	Mat rMat = cv::getRotationMatrix2D (ptC, dAngle, 1);
	rMat.at<double> (0, 2) -= ptLT_rotate.x - 3;
	rMat.at<double> (1, 2) -= ptLT_rotate.y - 3;
	cv::warpAffine (matSrc, matROI, rMat, sizePadding);
}

void CCOEFF_Denominator (Mat& matSrc, s_TemplData* pTemplData, Mat& matResult, int iLayer)
{
	if (pTemplData->vecResultEqual1[iLayer])
	{
		matResult = Scalar::all (1);
		return;
	}
	double* q0 = 0, * q1 = 0, * q2 = 0, * q3 = 0;

	Mat sum, sqsum;
	cv::integral (matSrc, sum, sqsum, CV_64F);

	q0 = (double*)sqsum.data;
	q1 = q0 + pTemplData->vecPyramid[iLayer].cols;
	q2 = (double*)(sqsum.data + pTemplData->vecPyramid[iLayer].rows * sqsum.step);
	q3 = q2 + pTemplData->vecPyramid[iLayer].cols;

	double* p0 = (double*)sum.data;
	double* p1 = p0 + pTemplData->vecPyramid[iLayer].cols;
	double* p2 = (double*)(sum.data + pTemplData->vecPyramid[iLayer].rows * sum.step);
	double* p3 = p2 + pTemplData->vecPyramid[iLayer].cols;

	int sumstep = sum.data ? (int)(sum.step / sizeof (double)) : 0;
	int sqstep = sqsum.data ? (int)(sqsum.step / sizeof (double)) : 0;

	double dTemplMean0 = pTemplData->vecTemplMean[iLayer][0];
	double dTemplNorm = pTemplData->vecTemplNorm[iLayer];
	double dInvArea = pTemplData->vecInvArea[iLayer];

	int i, j;
	for (i = 0; i < matResult.rows; i++)
	{
		float* rrow = matResult.ptr<float> (i);
		int idx = i * sumstep;
		int idx2 = i * sqstep;

		for (j = 0; j < matResult.cols; j += 1, idx += 1, idx2 += 1)
		{
			double num = rrow[j], t;
			double wndMean2 = 0, wndSum2 = 0;

			t = p0[idx] - p1[idx] - p2[idx] + p3[idx];
			wndMean2 += t * t;
			num -= t * dTemplMean0;
			wndMean2 *= dInvArea;

			t = q0[idx2] - q1[idx2] - q2[idx2] + q3[idx2];
			wndSum2 += t;

			double diff2 = MAX (wndSum2 - wndMean2, 0);
			if (diff2 <= min (0.5, 10 * FLT_EPSILON * wndSum2))
				t = 0; // avoid rounding errors
			else
				t = std::sqrt (diff2) * dTemplNorm;

			if (fabs (num) < t)
				num /= t;
			else if (fabs (num) < t * 1.125)
				num = num > 0 ? 1 : -1;
			else
				num = 0;

			rrow[j] = (float)num;
		}
	}
}

Size GetBestRotationSize (Size sizeSrc, Size sizeDst, double dRAngle)
{
	double dRAngle_radian = dRAngle * D2R;
	Point ptLT (0, 0), ptLB (0, sizeSrc.height - 1), ptRB (sizeSrc.width - 1, sizeSrc.height - 1), ptRT (sizeSrc.width - 1, 0);
	Point2f ptCenter ((sizeSrc.width - 1) / 2.0f, (sizeSrc.height - 1) / 2.0f);
	Point2f ptLT_R = ptRotatePt2f (Point2f (ptLT), ptCenter, dRAngle_radian);
	Point2f ptLB_R = ptRotatePt2f (Point2f (ptLB), ptCenter, dRAngle_radian);
	Point2f ptRB_R = ptRotatePt2f (Point2f (ptRB), ptCenter, dRAngle_radian);
	Point2f ptRT_R = ptRotatePt2f (Point2f (ptRT), ptCenter, dRAngle_radian);

	float fTopY = max (max (ptLT_R.y, ptLB_R.y), max (ptRB_R.y, ptRT_R.y));
	float fBottomY = min (min (ptLT_R.y, ptLB_R.y), min (ptRB_R.y, ptRT_R.y));
	float fRightX = max (max (ptLT_R.x, ptLB_R.x), max (ptRB_R.x, ptRT_R.x));
	float fLeftX = min (min (ptLT_R.x, ptLB_R.x), min (ptRB_R.x, ptRT_R.x));

	if (dRAngle > 360)
		dRAngle -= 360;
	else if (dRAngle < 0)
		dRAngle += 360;

	if (fabs (fabs (dRAngle) - 90) < VISION_TOLERANCE || fabs (fabs (dRAngle) - 270) < VISION_TOLERANCE)
		return Size (sizeSrc.height, sizeSrc.width);
	else if (fabs (dRAngle) < VISION_TOLERANCE || fabs (fabs (dRAngle) - 180) < VISION_TOLERANCE)
		return sizeSrc;

	double dAngle = dRAngle;

	if (dAngle > 0 && dAngle < 90)
		;
	else if (dAngle > 90 && dAngle < 180)
		dAngle -= 90;
	else if (dAngle > 180 && dAngle < 270)
		dAngle -= 180;
	else if (dAngle > 270 && dAngle < 360)
		dAngle -= 270;
	// else: nhánh không thể xảy ra (bản gốc gọi AfxMessageBox debug) -> bỏ.

	float fH1 = sizeDst.width * sin (dAngle * D2R) * cos (dAngle * D2R);
	float fH2 = sizeDst.height * sin (dAngle * D2R) * cos (dAngle * D2R);

	int iHalfHeight = (int)ceil (fTopY - ptCenter.y - fH1);
	int iHalfWidth = (int)ceil (fRightX - ptCenter.x - fH2);

	Size sizeRet (iHalfWidth * 2, iHalfHeight * 2);

	bool bWrongSize = (sizeDst.width < sizeRet.width && sizeDst.height > sizeRet.height)
		|| (sizeDst.width > sizeRet.width && sizeDst.height < sizeRet.height
			|| sizeDst.area () > sizeRet.area ());
	if (bWrongSize)
		sizeRet = Size (int (fRightX - fLeftX + 0.5), int (fTopY - fBottomY + 0.5));

	return sizeRet;
}

Point2f ptRotatePt2f (Point2f ptInput, Point2f ptOrg, double dAngle)
{
	double dHeight = ptOrg.y * 2;
	double dY1 = dHeight - ptInput.y, dY2 = dHeight - ptOrg.y;

	double dX = (ptInput.x - ptOrg.x) * cos (dAngle) - (dY1 - ptOrg.y) * sin (dAngle) + ptOrg.x;
	double dY = (ptInput.x - ptOrg.x) * sin (dAngle) + (dY1 - ptOrg.y) * cos (dAngle) + dY2;

	dY = -dY + dHeight;
	return Point2f ((float)dX, (float)dY);
}

void FilterWithScore (vector<s_MatchParameter>* vec, double dScore)
{
	sort (vec->begin (), vec->end (), compareScoreBig2Small);
	int iSize = (int)vec->size (), iIndexDelete = iSize + 1;
	for (int i = 0; i < iSize; i++)
	{
		if ((*vec)[i].dMatchScore < dScore)
		{
			iIndexDelete = i;
			break;
		}
	}
	if (iIndexDelete == iSize + 1) // không phần tử nào nhỏ hơn dScore
		return;
	vec->erase (vec->begin () + iIndexDelete, vec->end ());
}

void FilterWithRotatedRect (vector<s_MatchParameter>* vec, int iMethod, double dMaxOverLap)
{
	int iMatchSize = (int)vec->size ();
	RotatedRect rect1, rect2;
	for (int i = 0; i < iMatchSize - 1; i++)
	{
		if (vec->at (i).bDelete)
			continue;
		for (int j = i + 1; j < iMatchSize; j++)
		{
			if (vec->at (j).bDelete)
				continue;
			rect1 = vec->at (i).rectR;
			rect2 = vec->at (j).rectR;
			vector<Point2f> vecInterSec;
			int iInterSecType = cv::rotatedRectangleIntersection (rect1, rect2, vecInterSec);
			if (iInterSecType == cv::INTERSECT_NONE)
				continue;
			else if (iInterSecType == cv::INTERSECT_FULL)
			{
				int iDeleteIndex;
				if (iMethod == CV_TM_SQDIFF)
					iDeleteIndex = (vec->at (i).dMatchScore <= vec->at (j).dMatchScore) ? j : i;
				else
					iDeleteIndex = (vec->at (i).dMatchScore >= vec->at (j).dMatchScore) ? j : i;
				vec->at (iDeleteIndex).bDelete = true;
			}
			else
			{
				if (vecInterSec.size () < 3)
					continue;
				else
				{
					int iDeleteIndex;
					SortPtWithCenter (vecInterSec);
					double dArea = cv::contourArea (vecInterSec);
					double dRatio = dArea / rect1.size.area ();
					if (dRatio > dMaxOverLap)
					{
						if (iMethod == CV_TM_SQDIFF)
							iDeleteIndex = (vec->at (i).dMatchScore <= vec->at (j).dMatchScore) ? j : i;
						else
							iDeleteIndex = (vec->at (i).dMatchScore >= vec->at (j).dMatchScore) ? j : i;
						vec->at (iDeleteIndex).bDelete = true;
					}
				}
			}
		}
	}
	vector<s_MatchParameter>::iterator it;
	for (it = vec->begin (); it != vec->end ();)
	{
		if ((*it).bDelete)
			it = vec->erase (it);
		else
			++it;
	}
}

Point GetNextMaxLoc (Mat& matResult, Point ptMaxLoc, Size sizeTemplate, double& dMaxValue, double dMaxOverlap)
{
	int iStartX = (int)(ptMaxLoc.x - sizeTemplate.width * (1 - dMaxOverlap));
	int iStartY = (int)(ptMaxLoc.y - sizeTemplate.height * (1 - dMaxOverlap));
	cv::rectangle (matResult,
		Rect (iStartX, iStartY, (int)(2 * sizeTemplate.width * (1 - dMaxOverlap)), (int)(2 * sizeTemplate.height * (1 - dMaxOverlap))),
		Scalar (-1), CV_FILLED);
	Point ptNewMaxLoc;
	cv::minMaxLoc (matResult, 0, &dMaxValue, 0, &ptNewMaxLoc);
	return ptNewMaxLoc;
}

Point GetNextMaxLoc (Mat& matResult, Point ptMaxLoc, Size sizeTemplate, double& dMaxValue, double dMaxOverlap, s_BlockMax& blockMax)
{
	int iStartX = int (ptMaxLoc.x - sizeTemplate.width * (1 - dMaxOverlap));
	int iStartY = int (ptMaxLoc.y - sizeTemplate.height * (1 - dMaxOverlap));
	Rect rectIgnore (iStartX, iStartY, int (2 * sizeTemplate.width * (1 - dMaxOverlap)), int (2 * sizeTemplate.height * (1 - dMaxOverlap)));
	cv::rectangle (matResult, rectIgnore, Scalar (-1), CV_FILLED);
	blockMax.UpdateMax (rectIgnore);
	Point ptReturn;
	blockMax.GetMaxValueLoc (dMaxValue, ptReturn);
	return ptReturn;
}

void SortPtWithCenter (vector<Point2f>& vecSort)
{
	int iSize = (int)vecSort.size ();
	Point2f ptCenter;
	for (int i = 0; i < iSize; i++)
		ptCenter += vecSort[i];
	ptCenter /= (float)iSize;

	Point2f vecX (1, 0);

	vector<std::pair<Point2f, double>> vecPtAngle (iSize);
	for (int i = 0; i < iSize; i++)
	{
		vecPtAngle[i].first = vecSort[i];
		Point2f vec1 (vecSort[i].x - ptCenter.x, vecSort[i].y - ptCenter.y);
		float fNormVec1 = vec1.x * vec1.x + vec1.y * vec1.y;
		float fDot = vec1.x;

		if (vec1.y < 0)
			vecPtAngle[i].second = acos (fDot / fNormVec1) * R2D;
		else if (vec1.y > 0)
			vecPtAngle[i].second = 360 - acos (fDot / fNormVec1) * R2D;
		else
		{
			if (vec1.x - ptCenter.x > 0)
				vecPtAngle[i].second = 0;
			else
				vecPtAngle[i].second = 180;
		}
	}
	sort (vecPtAngle.begin (), vecPtAngle.end (), comparePtWithAngle);
	for (int i = 0; i < iSize; i++)
		vecSort[i] = vecPtAngle[i].first;
}

bool SubPixEsimation (vector<s_MatchParameter>* vec, double* dNewX, double* dNewY, double* dNewAngle, double dAngleStep, int iMaxScoreIndex)
{
	// Az=S, (A.T)Az=(A.T)s, z = ((A.T)A).inv (A.T)s
	Mat matA (27, 10, CV_64F);
	Mat matZ (10, 1, CV_64F);
	Mat matS (27, 1, CV_64F);

	double dX_maxScore = (*vec)[iMaxScoreIndex].pt.x;
	double dY_maxScore = (*vec)[iMaxScoreIndex].pt.y;
	double dTheata_maxScore = (*vec)[iMaxScoreIndex].dMatchAngle;
	int iRow = 0;
	for (int theta = 0; theta <= 2; theta++)
	{
		for (int y = -1; y <= 1; y++)
		{
			for (int x = -1; x <= 1; x++)
			{
				double dX = dX_maxScore + x;
				double dY = dY_maxScore + y;
				double dT = (dTheata_maxScore + (theta - 1) * dAngleStep) * D2R;
				matA.at<double> (iRow, 0) = dX * dX;
				matA.at<double> (iRow, 1) = dY * dY;
				matA.at<double> (iRow, 2) = dT * dT;
				matA.at<double> (iRow, 3) = dX * dY;
				matA.at<double> (iRow, 4) = dX * dT;
				matA.at<double> (iRow, 5) = dY * dT;
				matA.at<double> (iRow, 6) = dX;
				matA.at<double> (iRow, 7) = dY;
				matA.at<double> (iRow, 8) = dT;
				matA.at<double> (iRow, 9) = 1.0;
				matS.at<double> (iRow, 0) = (*vec)[iMaxScoreIndex + (theta - 1)].vecResult[x + 1][y + 1];
				iRow++;
			}
		}
	}
	matZ = (matA.t () * matA).inv () * matA.t () * matS;
	Mat matZ_t;
	cv::transpose (matZ, matZ_t);
	double* dZ = matZ_t.ptr<double> (0);
	Mat matK1 = (cv::Mat_<double> (3, 3) <<
		(2 * dZ[0]), dZ[3], dZ[4],
		dZ[3], (2 * dZ[1]), dZ[5],
		dZ[4], dZ[5], (2 * dZ[2]));
	Mat matK2 = (cv::Mat_<double> (3, 1) << -dZ[6], -dZ[7], -dZ[8]);
	Mat matDelta = matK1.inv () * matK2;

	*dNewX = matDelta.at<double> (0, 0);
	*dNewY = matDelta.at<double> (1, 0);
	*dNewAngle = matDelta.at<double> (2, 0) * R2D;
	return true;
}

void DrawDashLine (Mat& matDraw, Point ptStart, Point ptEnd, Scalar color1, Scalar color2)
{
	cv::LineIterator itLine (matDraw, ptStart, ptEnd, 8, 0);
	int iCount = itLine.count;
	for (int i = 0; i < iCount; i += 1, itLine++)
	{
		if (i % 3 == 0)
		{
			(*itLine)[0] = (uchar)color2.val[0];
			(*itLine)[1] = (uchar)color2.val[1];
			(*itLine)[2] = (uchar)color2.val[2];
		}
		else
		{
			(*itLine)[0] = (uchar)color1.val[0];
			(*itLine)[1] = (uchar)color1.val[1];
			(*itLine)[2] = (uchar)color1.val[2];
		}
	}
}

void DrawMarkCross (Mat& matDraw, int iX, int iY, int iLength, Scalar color, int iThickness)
{
	if (matDraw.empty ())
		return;
	Point ptC (iX, iY);
	cv::line (matDraw, ptC - Point (iLength, 0), ptC + Point (iLength, 0), color, iThickness);
	cv::line (matDraw, ptC - Point (0, iLength), ptC + Point (0, iLength), color, iThickness);
}

} // namespace fpm
