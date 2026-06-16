// fpm_match.cpp — CFastMatch: LearnPattern + Match port từ MatchToolDlg.cpp,
// đã bỏ MFC (UpdateData/AfxMessageBox/imshow/list-control/PumpMessages).
#include "fpm_core.h"

#include <algorithm>
#include <cmath>
#include <cfloat>
#include <stdexcept>

namespace fpm {

using std::max;
using std::min;
using std::sort;
using std::vector;

// Đảm bảo ảnh là 8UC1 (app gốc load IMREAD_GRAYSCALE).
static Mat ToGray (const Mat& m)
{
	if (m.channels () == 1)
		return m;
	Mat g;
	cv::cvtColor (m, g, cv::COLOR_BGR2GRAY);
	return g;
}

void CFastMatch::LearnPattern (const Mat& matTemplate, const MatchParams& params)
{
	m_matTempl = ToGray (matTemplate);
	if (m_matTempl.empty ())
		throw std::invalid_argument ("LearnPattern: template image is empty");

	m_TemplData.clear ();

	int iTopLayer = GetTopLayer (&m_matTempl, (int)sqrt ((double)params.iMinReduceArea));
	cv::buildPyramid (m_matTempl, m_TemplData.vecPyramid, iTopLayer);
	s_TemplData* templData = &m_TemplData;
	templData->iBorderColor = cv::mean (m_matTempl).val[0] < 128 ? 255 : 0;
	int iSize = (int)templData->vecPyramid.size ();
	templData->resize (iSize);

	for (int i = 0; i < iSize; i++)
	{
		double invArea = 1. / ((double)templData->vecPyramid[i].rows * templData->vecPyramid[i].cols);
		Scalar templMean, templSdv;
		double templNorm = 0, templSum2 = 0;

		cv::meanStdDev (templData->vecPyramid[i], templMean, templSdv);
		templNorm = templSdv[0] * templSdv[0] + templSdv[1] * templSdv[1] + templSdv[2] * templSdv[2] + templSdv[3] * templSdv[3];

		if (templNorm < DBL_EPSILON)
			templData->vecResultEqual1[i] = true;

		templSum2 = templNorm + templMean[0] * templMean[0] + templMean[1] * templMean[1] + templMean[2] * templMean[2] + templMean[3] * templMean[3];
		templSum2 /= invArea;
		templNorm = std::sqrt (templNorm);
		templNorm /= std::sqrt (invArea); // care of accuracy here

		templData->vecInvArea[i] = invArea;
		templData->vecTemplMean[i] = templMean;
		templData->vecTemplNorm[i] = templNorm;
	}
	templData->bIsPatternLearned = true;
}

vector<s_SingleTargetMatch> CFastMatch::Match (const Mat& matSource, const MatchParams& params)
{
	vector<s_SingleTargetMatch> vecResult;

	Mat matSrc = ToGray (matSource);
	if (matSrc.empty () || m_matTempl.empty ())
		return vecResult;
	if ((m_matTempl.cols < matSrc.cols && m_matTempl.rows > matSrc.rows) || (m_matTempl.cols > matSrc.cols && m_matTempl.rows < matSrc.rows))
		return vecResult;
	if (m_matTempl.size ().area () > matSrc.size ().area ())
		return vecResult;
	if (!m_TemplData.bIsPatternLearned)
		return vecResult;

	int iTopLayer = GetTopLayer (&m_matTempl, (int)sqrt ((double)params.iMinReduceArea));

	vector<Mat> vecMatSrcPyr;
	if (params.bBitwiseNot)
	{
		Mat matNewSrc = 255 - matSrc;
		cv::buildPyramid (matNewSrc, vecMatSrcPyr, iTopLayer);
	}
	else
		cv::buildPyramid (matSrc, vecMatSrcPyr, iTopLayer);

	s_TemplData* pTemplData = &m_TemplData;

	// Stage 1: tầng đỉnh tìm góc + ROI thô
	double dAngleStep = atan (2.0 / max (pTemplData->vecPyramid[iTopLayer].cols, pTemplData->vecPyramid[iTopLayer].rows)) * R2D;

	vector<double> vecAngles;
	if (params.bToleranceRange)
	{
		if (params.dTolerance1 >= params.dTolerance2 || params.dTolerance3 >= params.dTolerance4)
			throw std::invalid_argument ("Match: tolerance range invalid (left must be < right)");
		for (double dAngle = params.dTolerance1; dAngle < params.dTolerance2 + dAngleStep; dAngle += dAngleStep)
			vecAngles.push_back (dAngle);
		for (double dAngle = params.dTolerance3; dAngle < params.dTolerance4 + dAngleStep; dAngle += dAngleStep)
			vecAngles.push_back (dAngle);
	}
	else
	{
		if (params.dToleranceAngle < VISION_TOLERANCE)
			vecAngles.push_back (0.0);
		else
		{
			for (double dAngle = 0; dAngle < params.dToleranceAngle + dAngleStep; dAngle += dAngleStep)
				vecAngles.push_back (dAngle);
			for (double dAngle = -dAngleStep; dAngle > -params.dToleranceAngle - dAngleStep; dAngle -= dAngleStep)
				vecAngles.push_back (dAngle);
		}
	}

	int iTopSrcW = vecMatSrcPyr[iTopLayer].cols, iTopSrcH = vecMatSrcPyr[iTopLayer].rows;
	Point2f ptCenter ((iTopSrcW - 1) / 2.0f, (iTopSrcH - 1) / 2.0f);

	int iSize = (int)vecAngles.size ();
	vector<s_MatchParameter> vecMatchParameter;
	vector<double> vecLayerScore (iTopLayer + 1, params.dScore);
	for (int iLayer = 1; iLayer <= iTopLayer; iLayer++)
		vecLayerScore[iLayer] = vecLayerScore[iLayer - 1] * 0.9;

	Size sizePat = pTemplData->vecPyramid[iTopLayer].size ();
	bool bCalMaxByBlock = (vecMatSrcPyr[iTopLayer].size ().area () / sizePat.area () > 500) && params.iMaxPos > 10;

	for (int i = 0; i < iSize; i++)
	{
		Mat matRotatedSrc, matR = cv::getRotationMatrix2D (ptCenter, vecAngles[i], 1);
		Mat matResult;
		Point ptMaxLoc;
		double dValue, dMaxVal;
		Size sizeBest = GetBestRotationSize (vecMatSrcPyr[iTopLayer].size (), pTemplData->vecPyramid[iTopLayer].size (), vecAngles[i]);

		float fTranslationX = (sizeBest.width - 1) / 2.0f - ptCenter.x;
		float fTranslationY = (sizeBest.height - 1) / 2.0f - ptCenter.y;
		matR.at<double> (0, 2) += fTranslationX;
		matR.at<double> (1, 2) += fTranslationY;
		cv::warpAffine (vecMatSrcPyr[iTopLayer], matRotatedSrc, matR, sizeBest, cv::INTER_LINEAR, cv::BORDER_CONSTANT, Scalar (pTemplData->iBorderColor));

		MatchTemplate (matRotatedSrc, pTemplData, matResult, iTopLayer, false);

		if (bCalMaxByBlock)
		{
			s_BlockMax blockMax (matResult, pTemplData->vecPyramid[iTopLayer].size ());
			blockMax.GetMaxValueLoc (dMaxVal, ptMaxLoc);
			if (dMaxVal < vecLayerScore[iTopLayer])
				continue;
			vecMatchParameter.push_back (s_MatchParameter (Point2f (ptMaxLoc.x - fTranslationX, ptMaxLoc.y - fTranslationY), dMaxVal, vecAngles[i]));
			for (int j = 0; j < params.iMaxPos + MATCH_CANDIDATE_NUM - 1; j++)
			{
				ptMaxLoc = GetNextMaxLoc (matResult, ptMaxLoc, pTemplData->vecPyramid[iTopLayer].size (), dValue, params.dMaxOverlap, blockMax);
				if (dValue < vecLayerScore[iTopLayer])
					break;
				vecMatchParameter.push_back (s_MatchParameter (Point2f (ptMaxLoc.x - fTranslationX, ptMaxLoc.y - fTranslationY), dValue, vecAngles[i]));
			}
		}
		else
		{
			cv::minMaxLoc (matResult, 0, &dMaxVal, 0, &ptMaxLoc);
			if (dMaxVal < vecLayerScore[iTopLayer])
				continue;
			vecMatchParameter.push_back (s_MatchParameter (Point2f (ptMaxLoc.x - fTranslationX, ptMaxLoc.y - fTranslationY), dMaxVal, vecAngles[i]));
			for (int j = 0; j < params.iMaxPos + MATCH_CANDIDATE_NUM - 1; j++)
			{
				ptMaxLoc = GetNextMaxLoc (matResult, ptMaxLoc, pTemplData->vecPyramid[iTopLayer].size (), dValue, params.dMaxOverlap);
				if (dValue < vecLayerScore[iTopLayer])
					break;
				vecMatchParameter.push_back (s_MatchParameter (Point2f (ptMaxLoc.x - fTranslationX, ptMaxLoc.y - fTranslationY), dValue, vecAngles[i]));
			}
		}
	}
	sort (vecMatchParameter.begin (), vecMatchParameter.end (), compareScoreBig2Small);

	int iDstW = pTemplData->vecPyramid[iTopLayer].cols, iDstH = pTemplData->vecPyramid[iTopLayer].rows;

	// (Bỏ block hiển thị debug imshow của bản gốc)

	// Stage 2: tinh chỉnh xuống từng tầng
	bool bSubPixelEstimation = params.bSubPixel;
	int  iStopLayer = params.bStopLayer1 ? 1 : 0;
	vector<s_MatchParameter> vecAllResult;
	for (int i = 0; i < (int)vecMatchParameter.size (); i++)
	{
		double dRAngle = -vecMatchParameter[i].dMatchAngle * D2R;
		Point2f ptLT = ptRotatePt2f (vecMatchParameter[i].pt, ptCenter, dRAngle);

		dAngleStep = atan (2.0 / max (iDstW, iDstH)) * R2D;
		vecMatchParameter[i].dAngleStart = vecMatchParameter[i].dMatchAngle - dAngleStep;
		vecMatchParameter[i].dAngleEnd = vecMatchParameter[i].dMatchAngle + dAngleStep;

		if (iTopLayer <= iStopLayer)
		{
			vecMatchParameter[i].pt = Point2d (ptLT * ((iTopLayer == 0) ? 1 : 2));
			vecAllResult.push_back (vecMatchParameter[i]);
		}
		else
		{
			for (int iLayer = iTopLayer - 1; iLayer >= iStopLayer; iLayer--)
			{
				dAngleStep = atan (2.0 / max (pTemplData->vecPyramid[iLayer].cols, pTemplData->vecPyramid[iLayer].rows)) * R2D;
				vector<double> vecAngles2;
				double dMatchedAngle = vecMatchParameter[i].dMatchAngle;
				if (params.bToleranceRange)
				{
					for (int k = -1; k <= 1; k++)
						vecAngles2.push_back (dMatchedAngle + dAngleStep * k);
				}
				else
				{
					if (params.dToleranceAngle < VISION_TOLERANCE)
						vecAngles2.push_back (0.0);
					else
						for (int k = -1; k <= 1; k++)
							vecAngles2.push_back (dMatchedAngle + dAngleStep * k);
				}
				Point2f ptSrcCenter ((vecMatSrcPyr[iLayer].cols - 1) / 2.0f, (vecMatSrcPyr[iLayer].rows - 1) / 2.0f);
				int iSize2 = (int)vecAngles2.size ();
				vector<s_MatchParameter> vecNewMatchParameter (iSize2);
				int iMaxScoreIndex = 0;
				double dBigValue = -1;
				for (int j = 0; j < iSize2; j++)
				{
					Mat matResult, matRotatedSrc;
					double dMaxValue = 0;
					Point ptMaxLoc;
					GetRotatedROI (vecMatSrcPyr[iLayer], pTemplData->vecPyramid[iLayer].size (), ptLT * 2, vecAngles2[j], matRotatedSrc);

					MatchTemplate (matRotatedSrc, pTemplData, matResult, iLayer, params.bUseSIMD);
					cv::minMaxLoc (matResult, 0, &dMaxValue, 0, &ptMaxLoc);
					vecNewMatchParameter[j] = s_MatchParameter (ptMaxLoc, dMaxValue, vecAngles2[j]);

					if (vecNewMatchParameter[j].dMatchScore > dBigValue)
					{
						iMaxScoreIndex = j;
						dBigValue = vecNewMatchParameter[j].dMatchScore;
					}
					// subpixel: ghi lại lưới 3x3 quanh đỉnh nếu không nằm ở biên
					if (ptMaxLoc.x == 0 || ptMaxLoc.y == 0 || ptMaxLoc.x == matResult.cols - 1 || ptMaxLoc.y == matResult.rows - 1)
						vecNewMatchParameter[j].bPosOnBorder = true;
					if (!vecNewMatchParameter[j].bPosOnBorder)
					{
						for (int y = -1; y <= 1; y++)
							for (int x = -1; x <= 1; x++)
								vecNewMatchParameter[j].vecResult[x + 1][y + 1] = matResult.at<float> (ptMaxLoc + Point (x, y));
					}
				}
				if (vecNewMatchParameter[iMaxScoreIndex].dMatchScore < vecLayerScore[iLayer])
					break;
				if (bSubPixelEstimation
					&& iLayer == 0
					&& (!vecNewMatchParameter[iMaxScoreIndex].bPosOnBorder)
					&& iMaxScoreIndex != 0
					&& iMaxScoreIndex != 2)
				{
					double dNewX = 0, dNewY = 0, dNewAngle = 0;
					SubPixEsimation (&vecNewMatchParameter, &dNewX, &dNewY, &dNewAngle, dAngleStep, iMaxScoreIndex);
					vecNewMatchParameter[iMaxScoreIndex].pt = Point2d (dNewX, dNewY);
					vecNewMatchParameter[iMaxScoreIndex].dMatchAngle = dNewAngle;
				}

				double dNewMatchAngle = vecNewMatchParameter[iMaxScoreIndex].dMatchAngle;

				// đưa toạ độ về (0,0) của ảnh xoay (GetRotatedROI)
				Point2f ptPaddingLT = ptRotatePt2f (ptLT * 2, ptSrcCenter, dNewMatchAngle * D2R) - Point2f (3, 3);
				Point2f pt (vecNewMatchParameter[iMaxScoreIndex].pt.x + ptPaddingLT.x, vecNewMatchParameter[iMaxScoreIndex].pt.y + ptPaddingLT.y);
				pt = ptRotatePt2f (pt, ptSrcCenter, -dNewMatchAngle * D2R);

				if (iLayer == iStopLayer)
				{
					vecNewMatchParameter[iMaxScoreIndex].pt = pt * (iStopLayer == 0 ? 1 : 2);
					vecAllResult.push_back (vecNewMatchParameter[iMaxScoreIndex]);
				}
				else
				{
					vecMatchParameter[i].dMatchAngle = dNewMatchAngle;
					vecMatchParameter[i].dAngleStart = vecMatchParameter[i].dMatchAngle - dAngleStep / 2;
					vecMatchParameter[i].dAngleEnd = vecMatchParameter[i].dMatchAngle + dAngleStep / 2;
					ptLT = pt;
				}
			}
		}
	}
	FilterWithScore (&vecAllResult, params.dScore);

	// lọc chồng lấp
	iDstW = pTemplData->vecPyramid[iStopLayer].cols * (iStopLayer == 0 ? 1 : 2);
	iDstH = pTemplData->vecPyramid[iStopLayer].rows * (iStopLayer == 0 ? 1 : 2);

	for (int i = 0; i < (int)vecAllResult.size (); i++)
	{
		Point2f ptLT, ptRT, ptRB, ptLB;
		double dRAngle = -vecAllResult[i].dMatchAngle * D2R;
		ptLT = vecAllResult[i].pt;
		ptRT = Point2f (ptLT.x + iDstW * (float)cos (dRAngle), ptLT.y - iDstW * (float)sin (dRAngle));
		ptLB = Point2f (ptLT.x + iDstH * (float)sin (dRAngle), ptLT.y + iDstH * (float)cos (dRAngle));
		ptRB = Point2f (ptRT.x + iDstH * (float)sin (dRAngle), ptRT.y + iDstH * (float)cos (dRAngle));
		vecAllResult[i].rectR = RotatedRect (ptLT, ptRT, ptRB);
	}
	FilterWithRotatedRect (&vecAllResult, CV_TM_CCOEFF_NORMED, params.dMaxOverlap);

	sort (vecAllResult.begin (), vecAllResult.end (), compareScoreBig2Small);

	int iMatchSize = (int)vecAllResult.size ();
	if (iMatchSize == 0)
		return vecResult;
	int iW = pTemplData->vecPyramid[0].cols, iH = pTemplData->vecPyramid[0].rows;

	for (int i = 0; i < iMatchSize; i++)
	{
		s_SingleTargetMatch sstm;
		double dRAngle = -vecAllResult[i].dMatchAngle * D2R;

		sstm.ptLT = vecAllResult[i].pt;
		sstm.ptRT = Point2d (sstm.ptLT.x + iW * cos (dRAngle), sstm.ptLT.y - iW * sin (dRAngle));
		sstm.ptLB = Point2d (sstm.ptLT.x + iH * sin (dRAngle), sstm.ptLT.y + iH * cos (dRAngle));
		sstm.ptRB = Point2d (sstm.ptRT.x + iH * sin (dRAngle), sstm.ptRT.y + iH * cos (dRAngle));
		sstm.ptCenter = Point2d ((sstm.ptLT.x + sstm.ptRT.x + sstm.ptRB.x + sstm.ptLB.x) / 4, (sstm.ptLT.y + sstm.ptRT.y + sstm.ptRB.y + sstm.ptLB.y) / 4);
		sstm.dMatchedAngle = -vecAllResult[i].dMatchAngle;
		sstm.dMatchScore = vecAllResult[i].dMatchScore;

		if (sstm.dMatchedAngle < -180)
			sstm.dMatchedAngle += 360;
		if (sstm.dMatchedAngle > 180)
			sstm.dMatchedAngle -= 360;
		vecResult.push_back (sstm);

		if (i + 1 == params.iMaxPos)
			break;
	}
	return vecResult;
}

} // namespace fpm
