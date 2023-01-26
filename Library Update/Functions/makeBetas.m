function makeBetas(Params)
% PURPOSE: This function creates the beta signals used in Novy-Marx and
% Velikov (2021a)
%------------------------------------------------------------------------------------------
% USAGE:   
% makeBetas(Params)              % Turns the CRSP daily file into matrices
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -Params - a structure containing input parameter values
%             -Params.directory - directory where the setup_library.m was unzipped
%             -Params.username - WRDS username
%             -Params.pass - WRDS password 
%             -Params.domesticCommonEquityShareFlag - flag indicating whether to leave domestic common share equity (share code 10 or 11) only
%             -Params.SAMPLE_START - sample start date
%             -Params.SAMPLE_END - sample end dates
%             -Params.COMPUSTATVariablesFileName - Either name of file ('COMPUSTAT Variable Names.csv' included with library) or 'All' to download all ~1000 COMPUSTAT variables.
%             -Params.driverLocation - location of WRDS PostgreSQL JDBC Driver (included with library)
%             -Params.tcosts - type of trading costs to construct: 'full' - low-freq 4-measures combo + TAQ + ISSM; 'lf_combo' - low-freq 4-measures combo; 'gibbs' - just gibbs
%------------------------------------------------------------------------------------------
% Output:
%        -None
%------------------------------------------------------------------------------------------
% Examples:
%
% makeBetas(Params)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Frazzini, A. and L. Pedersen, 2014, Betting against beta, Journal of
%  Financial Economics, 111 (1): 1-25
%  2. Novy-Marx, R. and M. Velikov, 2021a, Betting against betting against
%  eta, Journal of Financial Economics, Forthcoming.
%  3. Novy-Marx, R. and M. Velikov, 2021b, Assaying anomalies, Working paper.

fprintf('\n\n\nNow working on making the betas. Run started at %s.\n',char(datetime('now')));


fprintf('\n\n\nMaking Frazzini-Pedersen (2014) betas first.\n');
load dret
load ff
load dff
load ret
load dates
load ddates
dxret = dret - repmat(drf,1,cols(dret));

beta =nan(size(ret));

dret3=(1+dxret).*(1+lag(dxret,1,nan)).*(1+lag(dxret,2,nan))-1;
dmkt3=(1+dmkt).*(1+lag(dmkt,1,nan)).*(1+lag(dmkt,2,nan))-1;

for i=find(dates>=(100*(Params.SAMPLE_START+3)+1),1,'first'):length(dates)
    if i<60
        min_date=dates(1);
    else
        min_date=dates(i-59);
    end
    vert_index=find(floor(ddates/100)>=min_date & floor(ddates/100)<=dates(i));
    hor_ind=find(sum(isfinite(dret3(vert_index,:)),1)>=750 & sum(isfinite(dxret(vert_index(end-249:end),:)),1)>=120  & isfinite(dret(vert_index(end),:)));
    for k=1:length(hor_ind)
        j=hor_ind(k);
        temp=[log(1+dxret(vert_index,j)) log(1+dmkt(vert_index)) log(1+dret3(vert_index,j)) log(1+dmkt3(vert_index))];                
        temp((isnan(sum(temp,2))) | (sum(imag(temp)~=0,2)>0),:)=[];     
        temp2 = temp(end-249:end,1:2);
        temp2((isnan(sum(temp2,2))) | (sum(imag(temp2)~=0,2)>0),:)=[];
        stdev=std(temp2,1,1); 
        rho=corr(temp(:,3:4));
        beta(i,j)=rho(1,2)*stdev(1)/stdev(2);        
    end
end

bfp=beta*0.6+0.4; 

fprintf('\n\n\nMaking the rest of the betas next.\n');

bols=nan(size(ret)); % Ivo's benchmark - 1 year of daily data, 1 mkt lag, no shrinkage
bolsserr=nan(size(ret)); % Ivo's benchmark - 1 year of daily data, 1 mkt lag, no shrinkage
bdim=nan(size(ret)); % Dimson correction - add one more lag of mkt
bvck=nan(size(ret)); % Vasicek shrinkage, similar to what LSY use
bstd=nan(size(ret)); % What we would consider standard - 1 mkt lag, shrinkage to 1
bsw=nan(size(ret)); % Ivo's benchmarks

dmktL1 = lag(dmkt,1,nan);

dmktBounds=[min([-2*dmkt 4*dmkt],[],2) max([-2*dmkt 4*dmkt],[],2)];
dxretw=max(dxret,repmat(dmktBounds(:,1),1,size(dret,2)));
dxretw=min(dxretw,repmat(dmktBounds(:,2),1,size(dret,2)));

wvck=nan(size(ret)); % Initialize the weights for the Vasicek shrinkage

for i=find(dates>=(100*(Params.SAMPLE_START+1)+1),1,'first'):length(dates)
    if i<12
        min_date=dates(1);
    else
        min_date=dates(i-11);
    end

    vert_index=find(floor(ddates/100)>=min_date & floor(ddates/100)<=dates(i));
    hor_ind=find(sum(isfinite(dxret(vert_index,:)),1)>=120 & isfinite(dret(vert_index(end),:)));
    x1=[ones(size(vert_index)) dmkt(vert_index)];
    x2=[ones(size(vert_index)) dmkt(vert_index) dmktL1(vert_index)];
    for k=1:length(hor_ind)
        j=hor_ind(k);
        res=nanols(dxret(vert_index,j),x1); % Benchmark beta 
        bols(i,j)=res.beta(2); 
        bolsserr(i,j)=res.bstd(2); % For the Vasicek
        res=nanols(dxret(vert_index,j),x2); % Dimson correction - add 1 lag of mkt 
        bdim(i,j)=res.beta(2)+res.beta(3);
        res=nanols(dxretw(vert_index,j),x1); % Ivo's betas - use the winsorized returns (dxretw)
        bsw(i,j)=res.beta(2);
    end
    
    % Apply the Vasicek shrinkage (Q about the weights?)
    sigmaSqI=bolsserr(i,:).^2;
    sigmaSqT=nanstd(bols(i,:))^2;
    wvck(i,:)=sigmaSqT./(sigmaSqT+sigmaSqI);
    bvck(i,:)=wvck(i,:).*bols(i,:)+(1-wvck(i,:))*nanmean(bols(i,:));
    
    % Apply a simple shrinkage to the Dimson estimate
    bstd=bdim*0.6+0.4;
end

save Data/betas bols bdim bsw bvck bstd bfp 
save Data/bols bols
save Data/bdim bdim
save Data/bsw bsw
save Data/bvck bvck
save Data/bstd bstd
save Data/bfp bfp

fprintf('\n\n\nRun ended at %s.\n',char(datetime('now')));

