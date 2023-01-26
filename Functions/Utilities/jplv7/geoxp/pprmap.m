function [out]=pprmap(long,lat,data,varargin)
% PURPOSE: This function links a map and two scatterplots of projections found by ppr
%------------------------------------------------------------------------
% USAGE: [out]=pprmap(long,lat,data,direct,C,half,N,M,carte,label,symbol)
%   where :
%           long = n x 1 vector of coordinates on the first axis
%           lat = n x 1 vector of coordinates on the second axis
%           data = n x 1 vector of the variable to study on the first axis
%           direct = optional 1 x 2 vector  of the projections to be plotted. Default is [1 2]
%           C = optional size of the starting neighborhood for each search. Default is C=tan(80*pi/180)
%           half = optional number of steps without an increase in the index, at which time the neighborhood is halved. Default is 30
%           N = optional number of structure removal, N >=2. Default is N=2
%           M = optional number of random starts. Default is M=4
%           carte = n x 2 optionnal matrix giving the polygons of the edges of the spatial units
%           label = n x 1 optionnal variable used to label selected observations
%           symbol = * symbol=1 : selected spatial units are marked with a different symbol
%                    * symbol=0 : selected spatial units are marked with a different color only (default)
%------------------------------------------------------------------------
% OUTPUTS: out = (n x 1) 0-1 variable: selected spatial units are marked with a 1  
%------------------------------------------------------------------------
% MANUAL: Select points on either the map or the ppr plots by clicking with the left mouse button
%         You can select points inside a polygon: - right click to set the first point of the polygon
%                                                 - left click to set the other points
%                                                 - right click to close the polygon
%         Change the active figure by pressing the 1-2 buttons
%         Selection is lost when you switch graph
%         To quit, click the middle button or press 'q'
%------------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr

close all;
figure(1);
figure(2);
set(figure(1),'Units','Normalized','Position',[0.0031 0.0957 0.9945 0.7539]);
set(figure(1),'Units','Pixel');
set(figure(2),'Units','Normalized','Position',[0.0031 0.0957 0.9945 0.7539]);
set(figure(2),'Units','Pixel');

obs1=zeros(size(long,1),1);
obs2=zeros(size(long,1),1);
c=0;
C=tan(80*pi/180);
l=0;
symbol=0;
x=data;
half=30;
N=2;
M=4;
direct=[1 2];
vectx=[];
vecty=[];

%creation of a menu to save
labels= str2mat(...
    '&File', ...
    '>&Save' ...
    );
calls= str2mat(...
    '',...
    'save pprfich  out1 out2 -ascii' ...
    );
makemenu(figure(1),labels,calls);
%%%%%%%%%%%%%%%%%%%%%%%


% handle the optionnal parameters
if ~isempty(varargin)
    t=size(varargin,2);
    if ~isempty(varargin{1})
        direct=varargin{1};
    end;
    if t>=2 & ~isempty(varargin{2})
        C=varargin{2};
    end;
    if t>=3 & ~isempty(varargin{3})
        half=varargin{3};
    end;
    if t>=4 & ~isempty(varargin{4})
        N=varargin{4};
    end;
    if t>=5 & ~isempty(varargin{5})
        M=varargin{5};
    end;
    if t>=6 & ~isempty(varargin{6})
        carte=varargin{6};
        c=1;
    end;
    if t>=7 & ~isempty(varargin{7})
        label=varargin{7};
        l=1;
    end;
    if t==8 & ~isempty(varargin{8})
        symbol=varargin{8};
    end;
end;

%%%%%%%%%%%%%%%%%%%%%

% Compute the ppr
[n,d]=size(x);
muhat=mean(x);
[V,D]=eig(cov(x));
xc=x-ones(n,1)*muhat;
Z=((D)^(-1/2)*V'*xc')';
Zt=Z;
astar=zeros(d,N);
bstar=zeros(d,N);
ppmax=zeros(1,N);
for i=1:N
   [astar(:,i),bstar(:,i),ppmax(i)]=csppeda(Zt,C,half,M);
   Zt=csppstrtrem(Zt,astar(:,i),bstar(:,i));
end
proj1=[astar(:,direct(1)),bstar(:,direct(1))];
proj2=[astar(:,direct(2)),bstar(:,direct(2))];
Zp1=Z*proj1;
Zp2=Z*proj2;

%%%%%%%%%%%%%%%%%%

% Trace the maps
figure(1);
Axis1=subplot(1,2,1);
if c==1
    plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
end;
hold on;
plot(long,lat,'b.');
axis equal;
title('Map');
Xlim1=get(Axis1,'XLim');
Ylim1=get(Axis1,'YLim');

figure(2);
Axis1f2=subplot(1,2,1);
if c==1
    plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
end;
hold on;
plot(long,lat,'b.');
axis equal;
title('Map');
Xlim1f2=get(Axis1f2,'XLim');
Ylim1f2=get(Axis1f2,'YLim');
%%%%%%%%%%%%%%%%%%%%%

% Trace the ppr scatter plots
figure(1);
Axis2=subplot(1,2,2);
plot(Zp1(:,1),Zp1(:,2),'b.');
title('ppr scatter plot');
xlabel(['direction :',num2str(direct(1))]);
axis manual;
subplot(Axis1);
axis manual;
Xlim2=get(Axis2,'XLim');
Ylim2=get(Axis2,'YLim');


figure(2);
Axis2f2=subplot(1,2,2);
plot(Zp2(:,1),Zp2(:,2),'b.');
title('ppr scatter plot');
xlabel(['direction :',num2str(direct(2))]);
axis manual;
subplot(Axis1f2);
axis manual;
Xlim2f2=get(Axis2f2,'XLim');
Ylim2f2=get(Axis2f2,'YLim');
%%%%%%%%%%%%%%%%%%%%%

% Main loop
figure(1);
maptest1=0;
maptest2=0;
pprtest1=0;
pprtest2=0;
BUTTON=0;
fig=1;
while BUTTON~=2 & BUTTON~=113 % Stop when the user push the middle button or press 'q'
    Posfig=get(1,'Position');
    PosAx1=get(Axis1,'Position');
    PosAx2=get(Axis2,'Position');
    %redraw the graphs
    figure(1);
    subplot(Axis2);
    hold on;
    cla;
    Iselect1=find(obs1==1);
    Iunselect1=find(obs1==0);
    Iselect2=find(obs2==1);
    Iunselect2=find(obs2==0);
    obsT=(obs1 & obs2);
    IselectT=find(obsT==1);
    if ~isempty(Iunselect1)
      plot(Zp1(Iunselect1,1),Zp1(Iunselect1,2),'b.');
    end;
    if ~isempty(Iselect2)
        if symbol==1
            plot(Zp1(Iselect2,1),Zp1(Iselect2,2),'bd');
        else
            plot(Zp1(Iselect2,1),Zp1(Iselect2,2),'g.');
        end;
    end;
    if ~isempty(Iselect1)
        if maptest1==1
            if symbol==1
                plot(Zp1(Iselect1,1),Zp1(Iselect1,2),'b*');
            else
                plot(Zp1(Iselect1,1),Zp1(Iselect1,2),'r.');
            end;
        elseif pprtest1==1
            if symbol==1
                plot(Zp1(Iselect1,1),Zp1(Iselect1,2),'bo'); 
            else
                plot(Zp1(Iselect1,1),Zp1(Iselect1,2),'m.'); 
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
        end;
    end;
    if ~isempty(IselectT)
        plot(Zp1(IselectT,1),Zp1(IselectT,2),'c.');
    end;
    hold off;
    subplot(Axis1);
    hold on;
    cla;
    if c==1
        plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
    end;
    if ~isempty(Iunselect1)
      plot(long(Iunselect1),lat(Iunselect1),'b.');
    end;
    
    if ~isempty(Iselect2)
        if symbol==1
            plot(long(Iselect2),lat(Iselect2),'bd');
        else
            plot(long(Iselect2),lat(Iselect2),'g.');
        end;
    end;
    if ~isempty(Iselect1)
        if maptest1==1
            if symbol==1
                plot(long(Iselect1),lat(Iselect1),'b*');
            else
                plot(long(Iselect1),lat(Iselect1),'r.');
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
        elseif pprtest1==1
            if symbol==1
                plot(long(Iselect1),lat(Iselect1),'bo');
            else
                plot(long(Iselect1),lat(Iselect1),'m.');              
            end;
        end;
        if l==1
            Htex=text(long(Iselect1),lat(Iselect1),num2str(label(Iselect1)));
            set(Htex,'FontSize',8);
        end;
    end;      
    if ~isempty(IselectT)
        plot(long(IselectT),lat(IselectT),'c.');
    end;
    hold off;
    %%%%%%%%%%%%%%%%%%%%%%%%
    figure(2);
    subplot(Axis2f2);
    hold on;
    cla;
    Iselect2=find(obs2==1);
    Iunselect2=find(obs2==0);
    if ~isempty(Iunselect2)
      plot(Zp2(Iunselect2,1),Zp2(Iunselect2,2),'b.');
    end;
    if ~isempty(Iselect1)
        if symbol==1
            plot(Zp2(Iselect1,1),Zp2(Iselect1,2),'bd');
        else
            plot(Zp2(Iselect1,1),Zp2(Iselect1,2),'g.');
        end;
    end;
    if ~isempty(Iselect2)
        if maptest2==1
            if symbol==1
                plot(Zp2(Iselect2,1),Zp2(Iselect2,2),'b*');
            else
                plot(Zp2(Iselect2,1),Zp2(Iselect2,2),'r.');
            end;
        elseif pprtest2==1
            if symbol==1
                plot(Zp2(Iselect2,1),Zp2(Iselect2,2),'bo'); 
            else
                plot(Zp2(Iselect2,1),Zp2(Iselect2,2),'m.'); 
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
        end;
    end;
    if ~isempty(IselectT)
        plot(Zp2(IselectT,1),Zp2(IselectT,2),'c.');
    end;
    hold off;
    subplot(Axis1f2);
    hold on;
    cla;
    if c==1
        plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
    end;
    if ~isempty(Iunselect2)
      plot(long(Iunselect2),lat(Iunselect2),'b.');
    end;
    if ~isempty(Iselect1)
        if symbol==1
            plot(long(Iselect1),lat(Iselect1),'bd');
        else
            plot(long(Iselect1),lat(Iselect1),'g.');
        end;
    end;
    if ~isempty(Iselect2)
        if maptest2==1
            if symbol==1
                plot(long(Iselect2),lat(Iselect2),'b*');
            else
                plot(long(Iselect2),lat(Iselect2),'r.');
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
        elseif pprtest2==1
            if symbol==1
                plot(long(Iselect2),lat(Iselect2),'bo');
            else
                plot(long(Iselect2),lat(Iselect2),'m.');              
            end;
        end;
        if l==1
            Htex=text(long(Iselect2),lat(Iselect2),num2str(label(Iselect2)));
            set(Htex,'FontSize',8);
        end;
    end;    
    if ~isempty(IselectT)
        plot(long(IselectT),lat(IselectT),'c.');
    end;
    hold off;
    
    
    
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    figure(fig);
    [x,y,BUTTON]=ginput(1);
    if BUTTON==49
        fig=1;
        continue;
    elseif BUTTON==50
        fig=2;
        continue;
    end;
    currentpoint=get(fig,'CurrentPoint');
    Posfig=get(fig,'Position');
    if fig==1
        PosAx1=get(Axis1,'Position');
        PosAx2=get(Axis2,'Position');  
        obs=obs1;
        maptest=maptest1;
        pprtest=pprtest1;
        Zpp=Zp1;
    elseif fig==2
        PosAx1=get(Axis1f2,'Position');
        PosAx2=get(Axis2f2,'Position');
        obs=obs2;
        maptest=maptest2;
        pprtest=pprtest2;
        Zpp=Zp2;
    end;
    
    % map selection
    if (currentpoint(1)>=PosAx1(1)*Posfig(3)) & (currentpoint(1)<=(PosAx1(1)+PosAx1(3))*Posfig(3)) & (currentpoint(2)>=PosAx1(2)*Posfig(4)) & (currentpoint(2)<=(PosAx1(2)+PosAx1(4))*Posfig(4))
        if maptest==0      
            maptest=1;
            pprtest=0;
            obs=zeros(size(long,1),1);
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'point');   
        %%%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'poly');
        end;
        %%%%%%%%%%%%%%%%%%%
    %%%%%%%%%%%%%%%%%%%%%%%
    % scatterplot selection
    elseif (currentpoint(1)>=PosAx2(1)*Posfig(3)) & (currentpoint(1)<=(PosAx2(1)+PosAx2(3))*Posfig(3)) & (currentpoint(2)>=PosAx2(2)*Posfig(4)) & (currentpoint(2)<=(PosAx2(2)+PosAx2(4))*Posfig(4))
        if pprtest==0
            pprtest=1;
            maptest=0;
            obs=zeros(size(long,1),1);
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2
            obs=selectstat('scatter',obs,Zpp(:,1),'point',Zpp(:,2),x,y);
        %%%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            [obs,vectx,vecty]=selectstat('scatter',obs,Zpp(:,1),'poly',Zpp(:,2),x,y);
        end;
        %%%%%%%%%%%%%%%%%%%%
    end;
    if fig==1
        maptest1=maptest;
        obs1=obs;
        pprtest1=pprtest;
    elseif fig==2
        maptest2=maptest;
        obs2=obs;
        pprtest2=pprtest;
    end;
    %%%%%%%%%%%%%%%%%%%%%%
end;
out=obs1 | obs2;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%