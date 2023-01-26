function hl=makeCorwinSchultz()
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% This functions create the HL Effective Spread (!!!) measure from Corwin
% and Schultz (JF, 2014).

tic;
fprintf('Starting HL construction at:\n');
disp(datetime('now'));

load dbidlo
load daskhi
load ddates
load dprc
load ret
load dates
load dcfacpr

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Section II.A
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
hi=daskhi;
lo=dbidlo;

hi(dprc<0)=nan;
lo(dprc<0)=nan;

dprc=abs(dprc);
lclose=lag(dprc,1,nan).*dcfacpr./lag(dcfacpr,1,nan);


% Page 726: "If the day t+1 low is above the day t close, we assume that the price rose
% overnight from the close to the day t+1 low and decrease both the high and low
% for day t+1 by the amount of the overnight change when calculating spreads.
% Similarly, if the day t+1 high is below the day t close, we assume the price fell
% overnight from the close to the day t+1 high and increase the day t+1 high and
% low prices by the amount of this overnight decrease."
pchg=zeros(size(dprc));
pchg(dbidlo>lclose)=dbidlo(dbidlo>lclose)-lclose(dbidlo>lclose);
pchg(daskhi<lclose)=daskhi(daskhi<lclose)-lclose(daskhi<lclose);
lo=lo-pchg;
hi=hi-pchg;
clear pchg lclose daskhi dbidlo

lhi=lag(hi,1,nan).*dcfacpr./lag(dcfacpr,1,nan);
llo=lag(lo,1,nan).*dcfacpr./lag(dcfacpr,1,nan);

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Actual spread estimation
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

beta=(log(hi./lo)).^2+(log(lhi./llo)).^2; % Equation (7)
beta(hi<=0 | lo<=0)=nan;

gamma=(log(max(hi,lhi)./min(lo,llo))).^2; % Equation (10)
gamma(min(lo,llo)<=0)=nan;
clear lo hi ldlow ldhigh dprc llo lhi

const=3-2*sqrt(2);

alpha=(sqrt(2*beta)-sqrt(beta))/const - ...   % Equation (18)
      sqrt(gamma/const);
s=2*(exp(alpha)-1)./(1+exp(alpha)); % Equation (14)

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Section II.C
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Page 727: "The high–low estimator assumes that the expectation of a stock’s true variance over a 2-day period is twice as large as the expectation of the variance over
% a single day. Even if this is true in expectation, the observed 2-day variance may be more than twice as large as the single-day variance during volatile
% periods, in cases with a large overnight price change, or when the total return over the 2-day period is large relative to the intraday volatility. If the observed
% 2-day variance is large enough, the high–low spread estimate will be negative. For most of the analysis to follow, we set all negative 2-day spreads to zero
% before calculating monthly averages."
s(s<0)=0;

hl=nan(size(ret));

for i=1:length(dates)
    ind=find(floor(ddates/100)==dates(i));
    hor_index=sum(isfinite(s(ind,:)),1)>=12;
    hl(i,hor_index)=nanmean(s(ind,hor_index),1);
end

hl=real(hl);

fprintf('Done with HL at:\n');
disp(datetime('now'));
toc;

