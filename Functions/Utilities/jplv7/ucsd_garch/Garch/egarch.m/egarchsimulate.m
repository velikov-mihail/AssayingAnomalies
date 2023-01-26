function [simulatedata, H] = egarchsimulate(t,parameters,p,q, errors)
% PURPOSE:
%     EGARCH(P,Q) time series simulation
% 
% USAGE:
%     [simulatedata, H] = garchsimulate(t,parameters,p,q, errors)
% 
% INPUTS:
%     t: Length of the time series desired
%     parameters: a 1+2*p+q x 1 vector of inputs where p are ARCH coefs and Q are GARCH coefs
%                  should be [Const, Arch P, Abs Arch P, and then Garch P]
%     P: Positive, scalar integer representing a model order of the ARCH process
%     Q: Non-Negative scalar integer representing a model order of the GARCH 
%         process: Q is the number of lags of the lagged conditional variances included
%         Can be empty([]) for ARCH process
%     errors: The type of error being used, valid types are:
%             'NORMAL' - Gaussian Innovations
%             'STUDENTST' - T-distributed errors
%             'GED' - General Error Distribution
% 
% OUTPUTS:
%     simulatedata: A time series with GARCH variances and normal disturbances
%     H:  A vector of conditional variances used in making the time series
% 
% COMMENTS:
%     log H(t) = Omega + Alpha(1)*r_{t-1}/(sqrt(h(t-1))) + Alpha(2)*r_{t-2}^2/(sqrt(h(t-2))) +...
%                    + Alpha(P)*r_{t-p}^2/(sqrt(h(t-p)))+ Absolute Alpha(1)* abs(r_{t-1}^2/(sqrt(h(t-1)))) + ...
%                    + Absolute Alpha(P)* abs(r_{t-p}^2/(sqrt(h(t-p)))) +  Beta(1)* log(H(t-1))
%                    + Beta(2)*log(H(t-2))+...+ Beta(Q)*log(H(t-q))
%
%   This program generates 500 more than required to minimize any starting bias
%
% Author: Kevin Sheppard
% kksheppard@ucsd.edu
% Revision: 2    Date: 12/31/2001




[r,c]=size(parameters);

if r<c
    parameters=parameters';
end

if isempty(q)
   m=p;
else
   m  =  max(p,q);   
end

t=t+500;

if strcmp(errors,'NORMAL') | strcmp(errors,'STUDENTST') | strcmp(errors,'GED')
   if strcmp(errors,'NORMAL') 
      errortype = 1;
   elseif strcmp(errors,'STUDENTST') 
      errortype = 2;
   elseif strcmp(errors,'GED') 
      errortype = 3;
   end
else
   error('error must be one of the three strings NORMAL, STUDENTST, or GED');
end

constp=parameters(1);
archp=parameters(2:p+1);
absarchp=parameters(p+2:2*p+1);
garchp=parameters(2*p+2:2*p+q+1);

if errortype==2 | errortype==3
   nu=parameters(2*p+q+2);
   parameters=parameters(1:2*p+q+1);
end


UncondStd =  sqrt(constp/(1-sum(archp)-sum(garchp)));
h=UncondStd.^2*ones(t+m,1);
data=UncondStd*ones(t+m,1);
if errortype==1
   RandomNums=randn(t+m,1);
elseif errortype==2
   RandomNums=stdtdis_rnd(t+m,nu);
else
   RandomNums=gedrnd(t+m,nu);
end


T=size(data,1);
for t = (m + 1):T
   h(t) = exp(parameters' * [1 ; data(t-(1:p))./sqrt(h(t-(1:p))); abs(data(t-(1:p))./sqrt(h(t-(1:p)))); log(h(t-(1:q)))]);
   data(t)=RandomNums(t)*sqrt(h(t));
end

simulatedata=data((m+1+500):T);
H=h(m+1+500:T);
