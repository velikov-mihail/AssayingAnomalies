*	Gibbs estimation of the Roll model

	IML subroutines used to estimate roll model in SAS.
	
	July 2010
	
	Joel Hasbrouck
____________________________________________________________________________________________________

	RollGibbs Library 02.sas
	
	Running this program compiles IML modules needed to do Gibbs estimation of Roll model and 
	places them in a library called IMLStor.

	Note:
	There are three routines to draw (simulate) the trade direction indicators (the q(t)).
	qDraw		Is written for efficiency, but it may be difficult to follow.
				It is a block sampler.
				It can only be used when c and the variance of u are fixed.
	qDrawSlow	Is written for clarity. It draws the q one-at-a-time, sequentially.
				It can only be used when c and the variance of u are fixed.
	qDrawVec	This is like qDraw, but can be used when c and variance of u are time-varying.
				(THIS ROUTINE HAS NOT BEEN THOROUGHLY TESTED.)

____________________________________________________________________________________________________;

options nodate nocenter nonumber ps=70 ls=120 nomprint; 
libname this "D:\Gibbs 2022 update\This\";

%let Infinity=1e30;
%let eps=1e-30;

*______________________________________________________________________________________________

	Define subroutines that will be used in simulations.
 ______________________________________________________________________________________________;
proc iml;

start main;
reset storage=this.imlstor;
store module=_all_;
remove module=main;
show storage;
finish main;


*____________________________________________________________________________________________________

	RollGibbsBeta: Estimate Roll model with Gibbs sampler
	
	The return argument is parmOut[nSweeps,3]
	Column 1:	c
	Column 2: beta
	Column 3: varu
____________________________________________________________________________________________________;


%let Infinity=1e30;
%let eps=1e-30;

start RollGibbsBeta(parmOut, p, pm, q, nSweeps, regDraw, varuDraw, qDraw, varuStart, cStart, betaStart, printLevel);
	nObs = nrow(p);
	if nrow(q)^=nObs | nrow(pm)^=nObs then do;
		print 'RollGibbsBeta length mismatch';
		return;
	end;
	dp = p[2:nObs] - p[1:(nObs-1)];
	
	if qDraw then do; 	*	Initialize qs to price sign changes;
		qInitial = {1} // sign(dp);
		qInitial = qInitial # (q^=0);	*	Only initialize nonzero elements of q;
		q = qInitial;
	end;

	if varuStart<=0 then varuStart = 0.001;
	varu = varuStart;
	if cStart<=0 then cStart=0.01;
	c = cStart;
	if betaStart<=0 then betaStart=1;
	beta = betaStart;
	
	parmOut = j(nSweeps,3,.);

	do sweep=1 to nSweeps;

		dq =  q[2:nObs] - q[1:(nObs-1)];
		dpm = pm[2:nObs] - pm[1:(nObs-1)];

		if regDraw then do;
			priorMu = {0,1};
			postMu = priorMu;
			priorCov = diag({1,2});
			postCov = priorCov;
			X = colvec(dq) || colvec(dpm);
			rc = BayesRegressionUpdate(priorMu, priorCov, dp, X, varu, postMu, postCov);
			if printLevel>=2 then print postMu postCov;
			coeffLower={0,-&Infinity};
			coeffUpper=j(2,1,&Infinity);
			coeffDraw = mvnrndT(postMu, postCov, coeffLower, coeffUpper);
			if printLevel>=2 then print coeffDraw;
			c = coeffDraw[1];
			beta = coeffDraw[2];
		end;

		if varuDraw then do;
			u = dp - c*dq - beta*dpm;
			priorAlpha = 1.e-12;
			priorBeta = 1.e-12;
			postAlpha = .;
			postBeta = .;
			rc = BayesVarianceUpdate(priorAlpha, priorBeta, u, postAlpha, postBeta);
			x = (1/postBeta) * rand('gamma',postAlpha);
			varu = 1/x;
			sdu = sqrt(varu);
			if printLevel>=2 then print varu;
		end;

		if qDraw then do;
			qDrawPrintLevel = 0;
			p2 = p - beta*pm;
			call qDraw(p2, q, c, varu, qDrawPrintLevel);
		end;
		
		parmOut[sweep, 1]=c;
		parmOut[sweep, 2] = beta;
		parmOut[sweep, 3] = varu;
		
end;
finish RollGibbsBeta;


*______________________________________________________________________________________________

call qDraw(p, q, c, varu, printLevel)	makes new draws for q

parameters:
p		column vector of trade prices
q		column vector of qs (REPLACED ON RETURN)
c		cost parameter
varu	variance of disturbance
printLevel	used to generate debugging output

_______________________________________________________________________________________________;
start qDraw(p, q, c, varu, printLevel);
if nrow(p)^=nrow(q) then do;
	print "qDraw. p and q are of different lengths. p is " nrow(p) "x" ncol(p) "; q is " nrow(q) "x" ncol(q);
	abort;
end;
if nrow(c)^=1 then do;
	print "qDraw. c should be a scalar. It is " nrow(c) "x" ncol(c);
	abort;
end;
if nrow(varu)^=1 then do;
	print "qDraw. varu should be a scalar. It is " nrow(varu) "x" ncol(varu);
	abort;
end;
if printlevel>0 then print p q;
qNonzero = q^=0;
q = q || q;
p2 = p || p;
nSkip = 2;
modp = colvec( mod(1:nrow(p),nSkip) );
ru = uniform(j(nrow(p),1,0));
do iStart=0 to (nSkip-1);
	if printLevel>0 then print iStart [l="" r="qDraw. iStart:" f=1.];
	k = modp=iStart;
	jnz = loc( k & qNonzero );	*	These are the q's we'll be drawing.;
	if printLevel>0 then print jnz [l="Drawing q's for t=" f=3.];
	q[jnz,1] = 1;
	q[jnz,2] = -1;
	cq = c*q;
	v = p2 - cq;
	u = v[2:nrow(v),] - v[1:(nrow(v)-1),];
	if printLevel>0 then print u [l="u:"];
	s=(u##2)/(2*varu);
	if printLevel>0 then print s [l="s"];
	sSum = (s//{0 0}) + ({0 0}//s);
	if printLevel>0 then print sSum [l="sSum (before reduction)"];
	sSum = sSum[jnz,];
	if printLevel>0 then print sSum [l="sSum (after reduction)"];
	logOdds = sSum[,2] - sSum[,1];
	*	Make sure that we won't get overflow when we call exp();
	logOkay = logOdds<500;
	Odds = exp(logOkay#logOdds);
	pBuy = Odds/(1+Odds);
	pBuy = logOkay#pBuy + ^logOkay;
	if printLevel>0 then print pBuy [f=e10.];
	qknz = 1 - 2*(ru[jnz]>pBuy);
	q[jnz,1] = qknz;
	if istart<(nSkip-1) then q[jnz,2] = qknz;
end;
q = q[,1];
finish qDraw;

*______________________________________________________________________________________________

call qDrawVec(p, q, c, varu, printLevel)	makes new draws for q

parameters:
p		column vector of trade prices
q		column vector of qs (REPLACED ON RETURN)
c		cost parameter (either a scalar or a Tx1 vector)
varu	variance of disturbance (either a scalar or a T-1 x 1 vector)
printLevel	used to generate debugging output

_______________________________________________________________________________________________;
start qDrawVec(p, q, c, varu, printLevel);
if nrow(p)^=nrow(q) then do;
	print "qDraw. p and q are of different lengths. p is " nrow(p) "x" ncol(p) "; q is " nrow(q) "x" ncol(q);
	abort;
end;
if nrow(c)^=1 & nrow(c)^=nrow(p) then do;
	print "qDraw. p is  " nrow(p) "x" ncol(p) "; c is " nrow(c) "x" ncol(c);
	abort;
end;
if nrow(varu)^=1 & nrow(varu)^=(nrow(p)-1) then do;
	print "qDraw. p is  " nrow(p) "x" ncol(p) "; varu is " nrow(varu) "x" ncol(varu) "(should  be T-1 x 1)";
	abort;
end;
if printlevel>0 then print p q;
qNonzero = q^=0;
if nrow(c)^=1 then c2 = c || c;
q = q || q;
p2 = p || p;
if nrow(varu)^=1 then varu2 = 2*(varu || varu);
else varu2 = 2*varu;
nSkip = 2;
modp = colvec( mod(1:nrow(p),nSkip) );
do iStart=0 to (nSkip-1);
	if printLevel>0 then print iStart [l="" r="qDraw. iStart:" f=1.];
	k = modp=iStart;
	jnz = loc( k & qNonzero );	*	These are the q's we'll be drawing.;
	if printLevel>0 then print jnz [l="Drawing q's for t=" f=3.];
	q[jnz,1] = 1;
	q[jnz,2] = -1;
	if nrow(c)=1 then cq = c*q;
	else cq = c2#q;
	v = p2 - cq;
	u = v[2:nrow(v),] - v[1:(nrow(v)-1),];
	if printLevel>0 then print u [l="u:"];
	if nrow(varu)=1 then s=(u##2)/(2*varu);
	else s = (u##2)/varu2;
	if printLevel>0 then print s [l="s"];
	sSum = (s//{0 0}) + ({0 0}//s);
	if printLevel>0 then print sSum [l="sSum (before reduction)"];
	sSum = sSum[jnz,];
	if printLevel>0 then print sSum [l="sSum (after reduction)"];
	logOdds = sSum[,2] - sSum[,1];
	*	Make sure that we won't get overflow when we call exp();
	logOkay = logOdds<500;
	Odds = exp(logOkay#logOdds);
	pBuy = Odds/(1+Odds);
	pBuy = logOkay#pBuy + ^logOkay;
	if printLevel>0 then print pBuy [f=e10.];
	ru = uniform( j(nrow(pBuy),1) );
	qknz = 1 - 2*(ru>pBuy);
	q[jnz,1] = qknz;
	if istart<(nSkip-1) then q[jnz,2] = qknz;
end;
q = q[,1];
finish qDrawVec;
*______________________________________________________________________________________________

call qDrawSlow(p, q, c, varu)	makes new draws for q
inputs:
p		column vector of trade prices
q		column vector of qs (REPLACED ON RETURN)
c		cost parameter
varu	variance of disturbance

 ______________________________________________________________________________________________;
start qDrawSlow(p, q, c, varu, PrintLevel);
T = nrow(p);
reset noname spaces=1;
if PrintLevel>0 then do;
	print "qDraw" T [r="T:"] varu [l="" r="varu:"] c [r="c:"];
	print (t(q));
end;
do s=1 to T;
	if PrintLevel>=2 then print s [r="s:"];
	if q[s]=0 then goto sNext;	* Don't make a draw if q=0 (p is a quote midpoint);
	prExp = j(1,2,0);
	if s<T then do;
		uAhead = (p[s+1] - p[s]) + c*{1 -1} - c*q[s+1];
		prExp = prExp - (uAhead##2)/(2*varu);
		if PrintLevel>=2 then print s [format=5. r='s'] (p[s])   [r='p[s]  '] (p[s+1]) [r='p[s+1]'] uAhead [r='uAhead'];
	end;
	if s>1 then do;
		uBack = (p[s] -  p[s-1]) + c*q[s-1] - c*{1 -1};
		prExp = prExp - (uBack##2)/(2*varu);
		if PrintLevel>=2 then print s [format=5. r='s'] (p[s-1]) [r='p[s-1]'] (p[s])   [r='p[s]  '] uBack  [r='uBack '];
	end;
	logOdds = prExp[1]-prExp[2];
	if PrintLevel>=2 then print logOdds [r='logOdds (in favor of buy)'];
	if abs(logOdds)>100 then q[s]=sign(logOdds);
	else do;
		pBuy = 1 - 1/(1+exp(logOdds));
		q[s] = 1 - 2*(rand('uniform')>PBuy);
	end;
sNext: end;
reset name;
return;
finish qDrawSlow;

*______________________________________________________________________________________________

rc = BayesVarianceUpdate(priorAlpha, priorBeta, u, postAlpha, postBeta)
	updates the variance posterior (inverted gamma)
inputs:
priorAlpha and priorBeta
u	vector of estimated disturbances
postAlpha and postBeta are updated on return to the posterior values
_______________________________________________________________________________________________;
start BayesVarianceUpdate(priorAlpha, priorBeta, u, postAlpha, postBeta);
postAlpha = priorAlpha + nrow(u)/2;
postBeta = priorBeta + (u##2)[+]/2;
return (0);
finish BayesVarianceUpdate;

*______________________________________________________________________________________________

rc = BayesRegressionUpdate(priorMu, priorCov, y, X, dVar, postMu, postCov)
	computes coefficient posteriors for normal Bayesian regression model
inputs:
priorMu and priorCov	coefficient priors (mean and covariance)
y	column vector of l.h.s. values
X	matrix of r.h.s. variables
dVar	error variance (taken as given)
postMu and postCov 	coefficient posteriors.
rc is a return code (0 if okay)
_______________________________________________________________________________________________;
start BayesRegressionUpdate(priorMu, priorCov, y, X, dVar, postMu, postCov);
if ncol(priorMu)^=1 then do;
	print "BayesRegressionUpdate. priorMu is " nrow(priorMu) "x" ncol(priorMu) " (should be a column vector)";
	return(-1);
end;
if nrow(X)<ncol(X) then do;
	print "BayesRegressionUpdate. X is " nrow(X) "x" ncol(X);
	return (-1);
end;
if nrow(X)^=nrow(y) | ncol(y)^=1 then do;
	print "BayesRegressionUpdate. X is " nrow(X) "x" ncol(X) "; y is " nrow(y) "x" ncol(y);
	return (-1);
end;
if nrow(priorMu)^=ncol(X) then do;
	print "BayesRegressionUpdate. X is " nrow(X) "x" ncol(X) "; priorMu is " nrow(priorMu) "x" ncol(priorMu)
		" (not conformable)";
	return (-1);
end;
if nrow(priorCov)^=ncol(priorCov) | nrow(priorCov)^=nrow(priorMu) then do;
	print "BayesRegressionUpdate. priorMu is " nrow(X) "x" ncol(X) "; priorCov is " nrow(priorCov) "x" ncol(priorCov);
	return (-1);
end;

covi = inv(priorCov);
Di = (1/dVar)*(t(X)*X) + covi;
D = inv(Di);
dd = (1/dVar)*t(X)*y + covi*priorMu;
postMu = D*dd;
postCov = D;
return (0);
finish BayesRegressionUpdate;

*______________________________________________________________________________________________

RandStdNormT(zlow,zhigh) returns a random draw from the standard normal distribution
truncated to the range (zlow, zhigh).
_______________________________________________________________________________________________;
start RandStdNormT(zlow,zhigh);
if zlow=-&Infinity & zhigh=&Infinity then return (normal(seed));
PROBNLIMIT = 6;
if zlow>PROBNLIMIT & (zhigh=&Infinity | zhigh>PROBNLIMIT) then return (zlow+100*&eps);
if zhigh<-PROBNLIMIT & (zlow=-&Infinity | zlow<-PROBNLIMIT) then return (zhigh-100*&eps);
if zlow=-&Infinity then plow=0;
else plow = probnorm(zlow);
if zhigh=&Infinity then phigh=1;
else phigh = probnorm(zhigh);
p = plow + rand('uniform')*(phigh-plow);
if p=1 then return (zlow + 100*eps);
if p=0 then return (zhigh - 100*eps);
return (probit(p));
finish RandStdNormT;

*______________________________________________________________________________________________

mvnrndT(mu, cov, vLower, vUpper) returns a random draw (a vector) from a multivariate normal 
distribution with mean mu and covariance matrix cov, truncated to the range (vLower, vUpper).
vLower and vUpper are vectors (conformable with mu) that specify the upper and lower truncation 
points for each component. 
_______________________________________________________________________________________________;
start mvnrndT(mu, cov, vLower, vUpper);
f = t(root(cov));
n = nrow(mu)*ncol(mu);
eta = j(n,1,0);
low = (vLower[1]-mu[1])/f[1,1];
high = (vUpper[1]-mu[1])/f[1,1];
eta[1] = RandStdNormT(low,high);
do k=2 to n;
	etasum = f[k,1:(k-1)]*eta[1:(k-1)];
	low = (vLower[k]-mu[k]-etasum)/f[k,k];
	high = (vUpper[k]-mu[k]-etasum)/f[k,k];
	eta[k] = RandStdNormT(low,high);
end;
return (colvec(mu)+f*eta);
finish mvnrndT;

run;
quit;


*______________________________________________________________________________________________

	Test the routines
 ______________________________________________________________________________________________;
proc iml;
	start main;
	call streaminit(1234);
	reset storage=this.imlstor;
	load;

	print 'Test of RandStdNorm:';
	x =RandStdNormT(.5,1);
	print x;
	
	print 'Test of mvnrndT:';
	mu={1 2};
	cov={1 .5, .5 1};
	vLower = {0 0};
	vUpper = {&infinity &infinity};
	x = mvnrndT(mu, cov, vLower, vUpper);
	print x;
	
	print 'Test of Bayesian normal regression update';
	nObs = 1000;
	nv = 2;
	x = j(nObs,nv);
	u = j(nObs,1);
	sdu = 2;
	do t=1 to nObs;
		x[t,1] = 1;
		u = sdu*rand('normal');
		do i=2 to nv;
			x[t,i] = rand('normal');
		end;
	end;
	y = x * colvec((1+(1:nv))) + u;
	priorMu={0,0};
	priorCov={&Infinity 0, 0 &Infinity};
	dVar = sdu*sdu;
	postMu = 0;
	postCov = 0;
	rc = BayesRegressionUpdate(priorMu, priorCov, y, X, dVar, postMu, postCov);
	print postMu;
	print postCov;
	priorAlpha = 1.e-6;
	priorBeta = 1.e-6;
	postAlpha = 0;
	postBeta = 0;
	u = y - X*postMu;
	rc = BayesVarianceUpdate(priorAlpha, priorBeta, u, postAlpha, postBeta);
	print postAlpha;
	print postBeta;
	finish main;
	run;
	quit;
	
proc iml;
	start main;
	call streaminit(1234);
	reset storage=this.imlstor;
	load;

	nObs = 250;
	sdm = sqrt(0.3##2 / 250);
	sdu = sqrt(0.2##2 / 250);
	print sdu;
	u = j(nObs,1,.);
	v = j(nObs,1,.);
	call randseed(12345);
	call randgen(u,'normal',0,sdu);
	call randgen(v,'normal',0,sdm);
	beta = 1.1;
	c = .04;
	q = j(nObs,1,.);
	call randgen(q,'uniform');
	q = sign(q-0.5);
	probZero = 0.6;
	z = j(nObs,1,.);
	call randgen(z,'uniform');
	q = (z>probZero)#q;
	p = j(nObs,1,.);
	m = 0;
	do t=1 to nObs;
		m = m + beta*v[t] + u[t];
		p[t] = m + c*q[t];
	end;
	pM = t(cusum(t(v)));
	
	nSweeps = 1000;
	regDraw = 1;
	varuDraw = 1;
	qDraw = 1;
	nDrop = 200;
	
	call RollGibbsBeta(parmOut, p, pm, q, nSweeps, regDraw, varuDraw, qDraw, 0,0,0,0);
	
	p2 = parmOut[(nDrop+1):nSweeps,];
	p2 = p2 || sqrt(p2[,3]);
	pm = p2[+,]/(nSweeps-nDrop);
	print pm;


	finish main;
run;
quit;		
	
